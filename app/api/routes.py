import asyncio
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config import settings
from app.core.exceptions import (
    SentimentAppException,
    InvalidTickerException,
    UnsupportedAssetException,
    TickerNotFoundException,
    JobNotFoundException,
    AnalysisRunNotFoundException,
)
from app.core.enums import PipelineStage, JobStatus
from app.core.models import AnalysisResult, Asset
from app.api.schemas import (
    AnalyzeRequest,
    HealthResponse,
    JobCompletedEvent,
    JobCreatedResponse,
    JobFailedEvent,
    JobProgressEvent,
    JobStatusResponse,
    RecentRunSummary,
    SSE_EVENT_COMPLETED,
    SSE_EVENT_FAILED,
    SSE_EVENT_PROGRESS,
)
from app.api.dependencies import get_client_ip
from app.db.database import get_db, SessionLocal
from app.db.repository import SentimentRepository
from app.services.ticker_service import TickerService
from app.services.finbert_service import FinBERTService
from app.services.orchestrator import AnalysisOrchestrator
from app.utils.lock_manager import TickerLockManager
from app.utils.rate_limiter import rate_limiter
from app.utils.logging import logger

router = APIRouter(prefix="/api/v1")

# Strong reference set to prevent background tasks from being garbage collected mid-execution (F-03)
_background_tasks: set[asyncio.Task] = set()


async def run_background_job(
    job_id: str,
    ticker: str,
    force_refresh: bool,
    enable_llm: bool,
    asset: Asset | None = None,
):
    """
    Durable in-app asynchronous background worker:
    Executes the 6-stage pipeline under a per-ticker mutex for request coalescing,
    persisting stage progress and completing the job record in SQLite.
    """
    lock = await TickerLockManager.get_lock(ticker)
    async with lock:
        db: Session = SessionLocal()
        try:
            async def on_progress(stage: PipelineStage, progress_pct: float, message: str):
                prog_db: Session = SessionLocal()
                try:
                    SentimentRepository.update_job_stage(prog_db, job_id, stage, progress_pct, message)
                finally:
                    prog_db.close()

            result = await asyncio.wait_for(
                AnalysisOrchestrator.run_pipeline(
                    ticker=ticker,
                    db=db,
                    force_refresh=force_refresh,
                    enable_llm=enable_llm,
                    on_progress=on_progress,
                    asset=asset,
                ),
                timeout=float(settings.PIPELINE_TIMEOUT_SECONDS),
            )
            SentimentRepository.complete_job(db, job_id, result.run_id)
            logger.info(f"Job {job_id} for {ticker} completed successfully -> Run ID: {result.run_id}")
        except asyncio.TimeoutError:
            timeout_msg = f"Pipeline execution timed out after {settings.PIPELINE_TIMEOUT_SECONDS}s"
            logger.error(f"Job {job_id} for {ticker} timed out: {timeout_msg}")
            SentimentRepository.fail_job(db, job_id, timeout_msg)
        except SentimentAppException as e:
            logger.warning(f"Job {job_id} for {ticker} failed with domain error: {e.message}")
            SentimentRepository.fail_job(db, job_id, e.message)
        except Exception as e:
            error_id = str(uuid.uuid4())
            logger.exception(f"Job {job_id} for {ticker} encountered unexpected error [error_id={error_id}]: {e}")
            SentimentRepository.fail_job(db, job_id, f"Internal error (ref {error_id})")
        finally:
            db.close()


@router.post(
    "/analyze",
    response_model=AnalysisResult | JobCreatedResponse,
    responses={
        200: {"description": "Instant cache hit with full AnalysisResult"},
        202: {"description": "Job created, processing in background"},
    },
)
async def analyze_ticker(
    req: AnalyzeRequest,
    response: Response,
    db: Session = Depends(get_db),
    client_ip: str = Depends(get_client_ip),
):
    """
    Analyzes current-day market sentiment for a US-listed equity or ETF.
    - If cached within the session bucket: returns 200 OK with full result instantly.
    - If uncached: creates an async job and returns 202 Accepted with SSE event stream URL.
    """
    # 1. IP Rate Limiting
    rate_limiter.check(client_ip, max_requests=settings.RATE_LIMIT_ANALYSIS_PER_MINUTE)

    # 2. Early ticker normalization & validation (bounded by TICKER_RESOLUTION_TIMEOUT_SECONDS)
    asset = await TickerService.resolve_ticker_async(req.ticker)
    normalized_ticker = asset.ticker

    # 3. Quick Cache Check
    if not req.force_refresh:
        from app.core.session_window import compute_session_window, compute_session_bucket
        session = compute_session_window()
        session_bucket, bucket_seconds = compute_session_bucket(session)
        cache_key = AnalysisOrchestrator.compute_cache_key(
            normalized_ticker, session_bucket, "yfinance_rss", req.enable_llm
        )
        cached = SentimentRepository.get_cached_run(db, cache_key, max_age_seconds=bucket_seconds)
        if cached:
            response.status_code = status.HTTP_200_OK
            return cached

    # 4. Create Background Job
    job_id = str(uuid.uuid4())
    SentimentRepository.create_job(db, job_id, normalized_ticker)

    # Launch in-app async background task with strong reference to prevent GC collection (F-03)
    task = asyncio.create_task(
        run_background_job(
            job_id=job_id,
            ticker=normalized_ticker,
            force_refresh=req.force_refresh,
            enable_llm=req.enable_llm,
            asset=asset,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    response.status_code = status.HTTP_202_ACCEPTED
    return JobCreatedResponse(
        job_id=job_id,
        ticker=normalized_ticker,
        status=JobStatus.QUEUED,
        poll_url=f"/api/v1/jobs/{job_id}",
        events_url=f"/api/v1/jobs/{job_id}/events",
        max_wait_seconds=settings.PIPELINE_TIMEOUT_SECONDS + 60,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    client_ip: str = Depends(get_client_ip),
):
    """Polling fallback for background job progression."""
    rate_limiter.check(client_ip, max_requests=settings.RATE_LIMIT_JOBS_PER_MINUTE)

    job = SentimentRepository.get_job(db, job_id)
    if not job:
        raise JobNotFoundException(job_id)
    return JobStatusResponse(
        job_id=job.id,
        ticker=job.ticker,
        status=JobStatus(job.status),
        stage=PipelineStage(job.stage),
        progress_pct=job.progress_pct,
        message=job.message,
        run_id=job.run_id,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/jobs/{job_id}/events")
async def stream_job_events(
    job_id: str,
    client_ip: str = Depends(get_client_ip),
):
    """
    Server-Sent Events (SSE) stream for real-time live pipeline progress.
    Emits progress, completed, and failed events.
    """
    rate_limiter.check(client_ip, max_requests=settings.RATE_LIMIT_JOBS_PER_MINUTE)

    def _fetch_job():
        db: Session = SessionLocal()
        try:
            return SentimentRepository.get_job(db, job_id)
        finally:
            db.close()

    # Unknown job on /jobs/{id}/events -> 404 before streaming
    initial_job = await asyncio.to_thread(_fetch_job)
    if not initial_job:
        raise JobNotFoundException(job_id)

    async def event_generator():
        last_stage = None
        last_pct = -1.0
        event_id = 1
        max_wait_seconds = settings.PIPELINE_TIMEOUT_SECONDS + 60
        start_time = asyncio.get_event_loop().time()

        while True:
            job = await asyncio.to_thread(_fetch_job)
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

            if job.status == JobStatus.FAILED.value:
                failed_evt = JobFailedEvent(
                    job_id=job.id,
                    status="FAILED",
                    error_code="JOB_FAILED",
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
                    message=job.message,
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_PROGRESS}\ndata: {progress_evt.model_dump_json()}\n\n"
                event_id += 1

            if asyncio.get_event_loop().time() - start_time > max_wait_seconds:
                timeout_evt = JobFailedEvent(
                    job_id=job.id,
                    status="FAILED",
                    error_code="STREAM_TIMEOUT",
                    error_message="SSE stream timeout",
                )
                yield f"id: {event_id}\nevent: {SSE_EVENT_FAILED}\ndata: {timeout_evt.model_dump_json()}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analysis/{run_id}", response_model=AnalysisResult)
async def get_analysis_result(run_id: str, db: Session = Depends(get_db)):
    """Fetch complete persisted diagnostic analysis and evidence chain for a specific run."""
    result = SentimentRepository.get_analysis_run(db, run_id)
    if not result:
        raise AnalysisRunNotFoundException(run_id)
    return result


@router.get("/history", response_model=list[RecentRunSummary])
async def get_search_history(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Retrieve recent searches and historical sentiment verdicts."""
    recent = SentimentRepository.get_recent_runs(db, limit=limit)
    return [RecentRunSummary(**r) for r in recent]


@router.get("/health", response_model=HealthResponse)
async def get_health_status(response: Response, db: Session = Depends(get_db)):
    """Health check endpoint validating SQLite, FinBERT initialization, and OpenRouter config."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
        SentimentRepository.get_recent_runs(db, limit=1)
        db_status = "HEALTHY"
    except Exception as e:
        logger.error(f"Health check database failure: {e}")
        db_ok = False
        db_status = "UNHEALTHY"

    finbert_status = FinBERTService.get_status()
    llm_configured = bool(settings.OPENROUTER_API_KEY)

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "DEGRADED"
    elif finbert_status == "FAILED":
        overall_status = "DEGRADED"
    else:
        overall_status = "UP"

    return HealthResponse(
        status=overall_status,
        database_status=db_status,
        finbert_status=finbert_status,
        llm_configured=llm_configured,
        app_env=settings.APP_ENV,
    )
