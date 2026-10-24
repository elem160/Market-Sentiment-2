import asyncio
import json
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Request, Response, status
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
from app.core.models import AnalysisResult, Asset, PipelineDeps
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
from app.services.job_manager import JobManager, get_default_job_manager
from app.utils.rate_limiter import rate_limiter
from app.utils.logging import logger
from app.utils.executors import run_db

router = APIRouter(prefix="/api/v1")

# Strong reference set to prevent background tasks from being garbage collected mid-execution (F-03)
_background_tasks: set[asyncio.Task] = get_default_job_manager()._background_tasks


async def run_background_job(
    job_id: str,
    ticker: str,
    force_refresh: bool,
    enable_llm: bool,
    asset: Asset | None = None,
    deps: PipelineDeps | None = None,
):
    """
    Durable in-app asynchronous background worker.
    Maintained for direct invocation and unit test backward compatibility.
    """
    try:
        async def on_progress(stage: PipelineStage, progress_pct: float, message: str):
            await run_db(SentimentRepository.update_job_stage, job_id, stage, progress_pct, message)

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
            timeout=float(settings.PIPELINE_TIMEOUT_SECONDS),
        )
        await run_db(SentimentRepository.complete_job, job_id, result.run_id)
        logger.info(f"Job {job_id} for {ticker} completed successfully -> Run ID: {result.run_id}")
    except asyncio.TimeoutError:
        timeout_msg = f"Pipeline execution timed out after {settings.PIPELINE_TIMEOUT_SECONDS}s"
        logger.error(f"Job {job_id} for {ticker} timed out: {timeout_msg}")
        await run_db(SentimentRepository.fail_job, job_id, timeout_msg)
    except SentimentAppException as e:
        logger.warning(f"Job {job_id} for {ticker} failed with domain error: {e.message}")
        await run_db(SentimentRepository.fail_job, job_id, e.message)
    except Exception as e:
        error_id = str(uuid.uuid4())
        logger.exception(f"Job {job_id} for {ticker} encountered unexpected error [error_id={error_id}]: {e}")
        await run_db(SentimentRepository.fail_job, job_id, f"Internal error (ref {error_id})")


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
    request: Request,
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

    from app.core.session_window import compute_session_window, compute_session_bucket
    session = compute_session_window()
    session_bucket, bucket_seconds = compute_session_bucket(session)
    cache_key = AnalysisOrchestrator.compute_cache_key(
        normalized_ticker, session_bucket, "yfinance_rss", req.enable_llm
    )

    # 3. Quick Cache Check
    if not req.force_refresh:
        cached = await run_db(SentimentRepository.get_cached_run, cache_key, bucket_seconds)
        if cached:
            response.status_code = status.HTTP_200_OK
            return cached

    # 4. Submit to JobManager
    job_manager: JobManager = (
        getattr(request.app.state, "job_manager", None)
        if hasattr(request, "app")
        else None
    )
    if job_manager is None:
        job_manager = get_default_job_manager()

    deps = getattr(request.app.state, "pipeline_deps", None) if hasattr(request, "app") else None

    job_id, coalesced, max_wait_seconds = await job_manager.submit(
        ticker=normalized_ticker,
        cache_key=cache_key,
        force_refresh=req.force_refresh,
        enable_llm=req.enable_llm,
        asset=asset,
        deps=deps,
    )

    response.status_code = status.HTTP_202_ACCEPTED
    return JobCreatedResponse(
        job_id=job_id,
        ticker=normalized_ticker,
        status=JobStatus.QUEUED,
        poll_url=f"/api/v1/jobs/{job_id}",
        events_url=f"/api/v1/jobs/{job_id}/events",
        max_wait_seconds=max_wait_seconds,
        coalesced=coalesced,
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
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
    request: Request,
    client_ip: str = Depends(get_client_ip),
):
    """
    Server-Sent Events (SSE) stream for real-time live pipeline progress.
    Emits progress, completed, and failed events with periodic heartbeats (: ping\n\n).
    """
    rate_limiter.check(client_ip, max_requests=settings.RATE_LIMIT_JOBS_PER_MINUTE)

    job_manager: JobManager = (
        getattr(request.app.state, "job_manager", None)
        if hasattr(request, "app")
        else None
    )
    if job_manager is None:
        job_manager = get_default_job_manager()

    # Pre-check if job exists (either in-flight or in DB) -> 404 before opening stream
    inflight = job_manager.get_job(job_id)
    if not inflight:
        initial_job = await run_db(SentimentRepository.get_job, job_id)
        if not initial_job:
            raise JobNotFoundException(job_id)

    return StreamingResponse(
        job_manager.stream_events(job_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/analysis/{run_id}", response_model=AnalysisResult)
def get_analysis_result(run_id: str, db: Session = Depends(get_db)):
    """Fetch complete persisted diagnostic analysis and evidence chain for a specific run."""
    result = SentimentRepository.get_analysis_run(db, run_id)
    if not result:
        raise AnalysisRunNotFoundException(run_id)
    return result


@router.get("/history", response_model=list[RecentRunSummary])
def get_search_history(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Retrieve recent searches and historical sentiment verdicts."""
    recent = SentimentRepository.get_recent_runs(db, limit=limit)
    return [RecentRunSummary(**r) for r in recent]


@router.get("/health", response_model=HealthResponse)
def get_health_status(response: Response, db: Session = Depends(get_db)):
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
