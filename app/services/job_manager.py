import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import Request

from app.api.schemas import (
    SSE_EVENT_COMPLETED,
    SSE_EVENT_FAILED,
    SSE_EVENT_PROGRESS,
    JobCompletedEvent,
    JobFailedEvent,
    JobProgressEvent,
)
from app.config import settings
from app.core.enums import JobStatus, PipelineStage
from app.core.exceptions import SentimentAppException
from app.core.models import Asset, PipelineDeps
from app.db.repository import SentimentRepository
from app.services.orchestrator import AnalysisOrchestrator
from app.utils.executors import run_db
from app.utils.logging import logger


@dataclass
class InflightJob:
    job_id: str
    ticker: str
    cache_key: str
    created_at_mono: float
    task: asyncio.Task | None = None
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    events: list[JobProgressEvent | JobCompletedEvent | JobFailedEvent] = field(default_factory=list)
    is_terminal: bool = False


class JobManager:
    """
    Durable in-app asynchronous Job Manager.
    - Global pipeline concurrency limit via asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)
    - Request coalescing by cache key (in-flight identical requests join the running job)
    - Queue position tracking and queue timeout (JOB_QUEUE_TIMEOUT_SECONDS)
    - In-process pub/sub event channel for SSE with heartbeat comments (: ping\\n\\n)
    - Graceful shutdown marking running jobs as CANCELLED in DB and awaiting tasks
    """

    def __init__(
        self,
        max_concurrent: int | None = None,
        queue_timeout_seconds: float | None = None,
        pipeline_timeout_seconds: float | None = None,
        heartbeat_seconds: float | None = None,
    ):
        self.max_concurrent = (
            max_concurrent
            if max_concurrent is not None
            else settings.MAX_CONCURRENT_PIPELINES
        )
        self.queue_timeout_seconds = (
            queue_timeout_seconds
            if queue_timeout_seconds is not None
            else float(settings.JOB_QUEUE_TIMEOUT_SECONDS)
        )
        self.pipeline_timeout_seconds = (
            pipeline_timeout_seconds
            if pipeline_timeout_seconds is not None
            else float(settings.PIPELINE_TIMEOUT_SECONDS)
        )
        self.heartbeat_seconds = (
            heartbeat_seconds
            if heartbeat_seconds is not None
            else float(settings.SSE_HEARTBEAT_SECONDS)
        )

        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._inflight: dict[str, InflightJob] = {}  # job_id -> InflightJob
        self._inflight_by_cache_key: dict[str, InflightJob] = {}  # cache_key -> InflightJob
        self._queue: list[str] = []  # list of queued job_ids waiting for semaphore
        self._lock = asyncio.Lock()  # protects internal structures
        self._background_tasks: set[asyncio.Task] = set()

    def get_max_wait_seconds(self) -> int:
        """Total maximum wait deadline covering queue timeout + pipeline execution + margin."""
        return int(self.queue_timeout_seconds + self.pipeline_timeout_seconds + 15)

    async def submit(
        self,
        ticker: str,
        cache_key: str,
        force_refresh: bool = False,
        enable_llm: bool = True,
        asset: Asset | None = None,
        deps: PipelineDeps | None = None,
    ) -> tuple[str, bool, int]:
        """
        Submit a ticker analysis request.
        Returns:
            tuple[job_id, coalesced, max_wait_seconds]
        """
        max_wait = self.get_max_wait_seconds()

        async with self._lock:
            # Check for existing in-flight job with matching cache key
            existing = self._inflight_by_cache_key.get(cache_key)
            if existing and not existing.is_terminal and existing.task and not existing.task.done():
                logger.info(
                    f"Coalescing request for ticker '{ticker}' onto in-flight job {existing.job_id}"
                )
                return existing.job_id, True, max_wait

            job_id = str(uuid.uuid4())
            await run_db(SentimentRepository.create_job, job_id, ticker)

            inflight = InflightJob(
                job_id=job_id,
                ticker=ticker,
                cache_key=cache_key,
                created_at_mono=time.monotonic(),
            )
            self._inflight[job_id] = inflight
            self._inflight_by_cache_key[cache_key] = inflight
            self._queue.append(job_id)

            task = asyncio.create_task(
                self._run_job(
                    inflight=inflight,
                    force_refresh=force_refresh,
                    enable_llm=enable_llm,
                    asset=asset,
                    deps=deps,
                )
            )
            inflight.task = task
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

            return job_id, False, max_wait

    def get_job(self, job_id: str) -> InflightJob | None:
        """Lookup an active in-flight job by id."""
        return self._inflight.get(job_id)

    async def subscribe(self, job_id: str) -> tuple[InflightJob | None, asyncio.Queue | None]:
        """
        Subscribe an SSE listener to an in-process job's event channel.
        Replays already emitted events so the subscriber is immediately caught up.
        """
        async with self._lock:
            inflight = self._inflight.get(job_id)
            if not inflight:
                return None, None
            q: asyncio.Queue = asyncio.Queue()
            for evt in inflight.events:
                q.put_nowait(evt)
            inflight.subscribers.add(q)
            return inflight, q

    async def unsubscribe(self, inflight: InflightJob, q: asyncio.Queue):
        """Unsubscribe an SSE listener."""
        async with self._lock:
            inflight.subscribers.discard(q)
            if inflight.is_terminal and not inflight.subscribers:
                self._inflight.pop(inflight.job_id, None)

    def _publish_event(
        self, inflight: InflightJob, event: JobProgressEvent | JobCompletedEvent | JobFailedEvent
    ):
        inflight.events.append(event)
        if isinstance(event, (JobCompletedEvent, JobFailedEvent)):
            inflight.is_terminal = True
        for q in list(inflight.subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    async def _update_waiting_queue_positions(self):
        """Update queued jobs with their new positions ahead in the queue."""
        async with self._lock:
            for idx, q_job_id in enumerate(self._queue):
                inflight = self._inflight.get(q_job_id)
                if not inflight:
                    continue
                msg = f"Waiting for a worker ({idx} ahead)"
                await run_db(
                    SentimentRepository.update_job_stage,
                    q_job_id,
                    PipelineStage.RESOLVING_TICKER,
                    0.0,
                    msg,
                )
                self._publish_event(
                    inflight,
                    JobProgressEvent(
                        job_id=q_job_id,
                        ticker=inflight.ticker,
                        status=JobStatus.QUEUED,
                        stage=PipelineStage.RESOLVING_TICKER,
                        progress_pct=0.0,
                        message=msg,
                    ),
                )

    async def _run_job(
        self,
        inflight: InflightJob,
        force_refresh: bool,
        enable_llm: bool,
        asset: Asset | None,
        deps: PipelineDeps | None,
    ):
        job_id = inflight.job_id
        ticker = inflight.ticker

        # Initial QUEUED event with queue position
        async with self._lock:
            queue_idx = self._queue.index(job_id) if job_id in self._queue else 0
            initial_msg = f"Waiting for a worker ({queue_idx} ahead)"

        self._publish_event(
            inflight,
            JobProgressEvent(
                job_id=job_id,
                ticker=ticker,
                status=JobStatus.QUEUED,
                stage=PipelineStage.RESOLVING_TICKER,
                progress_pct=0.0,
                message=initial_msg,
            ),
        )

        # Wait to acquire concurrency semaphore within queue timeout
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.queue_timeout_seconds,
            )
        except TimeoutError:
            async with self._lock:
                if job_id in self._queue:
                    self._queue.remove(job_id)
            fail_msg = "Queue wait timed out"
            logger.warning(
                f"Job {job_id} for {ticker} timed out waiting in queue after {self.queue_timeout_seconds}s"
            )
            await run_db(SentimentRepository.fail_job, job_id, fail_msg)
            self._publish_event(
                inflight,
                JobFailedEvent(
                    job_id=job_id,
                    status="FAILED",
                    error_code="QUEUE_TIMEOUT",
                    error_message=fail_msg,
                ),
            )
            await self._cleanup_job(inflight)
            await self._update_waiting_queue_positions()
            return
        except asyncio.CancelledError:
            async with self._lock:
                if job_id in self._queue:
                    self._queue.remove(job_id)
            await self._cleanup_job(inflight)
            raise

        # Acquired semaphore: remove from queue and notify remaining waiting jobs
        async with self._lock:
            if job_id in self._queue:
                self._queue.remove(job_id)
        await self._update_waiting_queue_positions()

        # Execute pipeline within PIPELINE_TIMEOUT_SECONDS
        try:
            async def on_progress(stage: PipelineStage, progress_pct: float, message: str):
                await run_db(SentimentRepository.update_job_stage, job_id, stage, progress_pct, message)
                self._publish_event(
                    inflight,
                    JobProgressEvent(
                        job_id=job_id,
                        ticker=ticker,
                        status=JobStatus.PROCESSING,
                        stage=stage,
                        progress_pct=progress_pct,
                        message=message,
                    ),
                )

            result = await asyncio.wait_for(
                AnalysisOrchestrator.run_pipeline(
                    ticker=ticker,
                    db=None,
                    force_refresh=force_refresh,
                    enable_llm=enable_llm,
                    on_progress=on_progress,
                    asset=asset,
                    deps=deps,
                ),
                timeout=self.pipeline_timeout_seconds,
            )
            await run_db(SentimentRepository.complete_job, job_id, result.run_id)
            self._publish_event(
                inflight,
                JobCompletedEvent(
                    job_id=job_id,
                    status="COMPLETED",
                    run_id=result.run_id,
                    message="Analysis complete.",
                ),
            )
            logger.info(f"Job {job_id} for {ticker} completed successfully -> Run ID: {result.run_id}")

        except TimeoutError:
            timeout_msg = f"Pipeline execution timed out after {self.pipeline_timeout_seconds}s"
            logger.error(f"Job {job_id} for {ticker} timed out: {timeout_msg}")
            await run_db(SentimentRepository.fail_job, job_id, timeout_msg)
            self._publish_event(
                inflight,
                JobFailedEvent(
                    job_id=job_id,
                    status="FAILED",
                    error_code="PIPELINE_TIMEOUT",
                    error_message=timeout_msg,
                ),
            )
        except asyncio.CancelledError:
            logger.info(f"Job {job_id} for {ticker} was cancelled")
            raise
        except SentimentAppException as e:
            logger.warning(f"Job {job_id} for {ticker} failed with domain error: {e.message}")
            await run_db(SentimentRepository.fail_job, job_id, e.message)
            self._publish_event(
                inflight,
                JobFailedEvent(
                    job_id=job_id,
                    status="FAILED",
                    error_code="JOB_FAILED",
                    error_message=e.message,
                ),
            )
        except Exception as e:
            error_id = str(uuid.uuid4())
            logger.exception(
                f"Job {job_id} for {ticker} encountered unexpected error [error_id={error_id}]: {e}"
            )
            err_msg = f"Internal error (ref {error_id})"
            await run_db(SentimentRepository.fail_job, job_id, err_msg)
            self._publish_event(
                inflight,
                JobFailedEvent(
                    job_id=job_id,
                    status="FAILED",
                    error_code="INTERNAL_ERROR",
                    error_message=err_msg,
                ),
            )
        finally:
            self._semaphore.release()
            await self._cleanup_job(inflight)
            await self._update_waiting_queue_positions()

    async def _cleanup_job(self, inflight: InflightJob):
        """Remove job from in-flight cache key mapping."""
        async with self._lock:
            if self._inflight_by_cache_key.get(inflight.cache_key) is inflight:
                self._inflight_by_cache_key.pop(inflight.cache_key, None)
            if inflight.is_terminal and not inflight.subscribers:
                self._inflight.pop(inflight.job_id, None)

    async def stream_events(self, job_id: str, request: Request) -> AsyncIterator[str]:
        """
        Stream Server-Sent Events (SSE) for a job.
        Uses in-process pub/sub event channel when the job is in this process,
        falling back to 1s DB polling when the job is not in memory.
        Emits heartbeat comments (: ping\\n\\n) every SSE_HEARTBEAT_SECONDS.
        """
        max_wait_seconds = self.get_max_wait_seconds()
        start_mono = time.monotonic()
        event_id = 1

        # Check in-process channel first
        inflight, queue = await self.subscribe(job_id)

        if inflight is not None and queue is not None:
            try:
                while True:
                    if await request.is_disconnected():
                        logger.debug(f"SSE client disconnected from job {job_id}")
                        break

                    now_mono = time.monotonic()
                    if now_mono - start_mono > max_wait_seconds:
                        timeout_evt = JobFailedEvent(
                            job_id=job_id,
                            status="FAILED",
                            error_code="STREAM_TIMEOUT",
                            error_message="SSE stream timeout",
                        )
                        yield f"id: {event_id}\nevent: {SSE_EVENT_FAILED}\ndata: {timeout_evt.model_dump_json()}\n\n"
                        break

                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=self.heartbeat_seconds)
                    except TimeoutError:
                        # Heartbeat interval elapsed: emit SSE comment
                        yield ": ping\n\n"
                        continue

                    if isinstance(event, JobProgressEvent):
                        yield f"id: {event_id}\nevent: {SSE_EVENT_PROGRESS}\ndata: {event.model_dump_json()}\n\n"
                        event_id += 1
                    elif isinstance(event, JobCompletedEvent):
                        yield f"id: {event_id}\nevent: {SSE_EVENT_COMPLETED}\ndata: {event.model_dump_json()}\n\n"
                        break
                    elif isinstance(event, JobFailedEvent):
                        yield f"id: {event_id}\nevent: {SSE_EVENT_FAILED}\ndata: {event.model_dump_json()}\n\n"
                        break
            finally:
                await self.unsubscribe(inflight, queue)
            return

        # Fallback to 1s DB polling when job is not in-process
        from app.core.exceptions import JobNotFoundException

        initial_job = await run_db(SentimentRepository.get_job, job_id)
        if not initial_job:
            raise JobNotFoundException(job_id)

        last_stage = None
        last_pct = -1.0
        last_heartbeat_mono = start_mono

        while True:
            if await request.is_disconnected():
                logger.debug(f"SSE client disconnected from job {job_id}")
                break

            now_mono = time.monotonic()
            if now_mono - start_mono > max_wait_seconds:
                timeout_evt = JobFailedEvent(
                    job_id=job_id,
                    status="FAILED",
                    error_code="STREAM_TIMEOUT",
                    error_message="SSE stream timeout",
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_FAILED}\ndata: {timeout_evt.model_dump_json()}\n\n"
                break

            # Send heartbeat comment if elapsed
            if now_mono - last_heartbeat_mono >= self.heartbeat_seconds:
                yield ": ping\n\n"
                last_heartbeat_mono = now_mono

            job = await run_db(SentimentRepository.get_job, job_id)
            if not job:
                failed_evt = JobFailedEvent(
                    job_id=job_id,
                    status="FAILED",
                    error_code="JOB_NOT_FOUND",
                    error_message=f"Job '{job_id}' not found.",
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_FAILED}\ndata: {failed_evt.model_dump_json()}\n\n"
                break

            if job.status == JobStatus.COMPLETED.value:
                completed_evt = JobCompletedEvent(
                    job_id=job.id,
                    status="COMPLETED",
                    run_id=job.run_id or "",
                    message=job.message or "Analysis complete.",
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_COMPLETED}\ndata: {completed_evt.model_dump_json()}\n\n"
                break

            if job.status in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
                failed_evt = JobFailedEvent(
                    job_id=job.id,
                    status="FAILED",
                    error_code="JOB_FAILED" if job.status == JobStatus.FAILED.value else "CANCELLED",
                    error_message=job.error_message or "Unknown failure",
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_FAILED}\ndata: {failed_evt.model_dump_json()}\n\n"
                break

            # Emit progress update if changed
            if job.stage != last_stage or abs(job.progress_pct - last_pct) > 0.04:
                last_stage = job.stage
                last_pct = job.progress_pct
                progress_evt = JobProgressEvent(
                    job_id=job.id,
                    ticker=job.ticker,
                    status=JobStatus(job.status),
                    stage=PipelineStage(job.stage),
                    progress_pct=job.progress_pct,
                    message=job.message or "",
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_PROGRESS}\ndata: {progress_evt.model_dump_json()}\n\n"
                event_id += 1

            await asyncio.sleep(1.0)

    async def shutdown(self, timeout: float = 10.0):
        """Gracefully cancel in-flight tasks and mark jobs CANCELLED in DB."""
        logger.info("JobManager shutting down: cancelling active tasks...")
        async with self._lock:
            active_jobs = list(self._inflight.values())
            tasks_to_await = []
            for inflight in active_jobs:
                try:
                    await run_db(SentimentRepository.cancel_job, inflight.job_id, "Server shutdown")
                except Exception as e:
                    logger.warning(f"Could not cancel job {inflight.job_id} in DB: {e}")

                self._publish_event(
                    inflight,
                    JobFailedEvent(
                        job_id=inflight.job_id,
                        status="FAILED",
                        error_code="CANCELLED",
                        error_message="Server shutdown",
                    ),
                )

                if inflight.task and not inflight.task.done():
                    inflight.task.cancel()
                    tasks_to_await.append(inflight.task)

            self._queue.clear()
            self._inflight_by_cache_key.clear()

        if tasks_to_await:
            await asyncio.wait(tasks_to_await, timeout=timeout)

    async def drain(self, timeout: float = 5.0):
        """Wait for background tasks to finish (used by test fixtures)."""
        pending = {t for t in self._background_tasks if not t.done()}
        if not pending:
            return
        _, still_running = await asyncio.wait(pending, timeout=timeout)
        for task in still_running:
            task.cancel()
        if still_running:
            await asyncio.gather(*still_running, return_exceptions=True)


_default_job_manager: JobManager | None = None


def get_default_job_manager() -> JobManager:
    global _default_job_manager
    if _default_job_manager is None:
        _default_job_manager = JobManager()
    return _default_job_manager


def set_default_job_manager(manager: JobManager | None):
    global _default_job_manager
    _default_job_manager = manager
