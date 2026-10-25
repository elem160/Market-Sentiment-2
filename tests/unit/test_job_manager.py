import asyncio
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from app.api.schemas import (
    SSE_EVENT_COMPLETED,
    SSE_EVENT_PROGRESS,
)
from app.core.enums import (
    AssetType,
    DecisionVerdict,
    JobStatus,
    PipelineMode,
    PipelineStage,
)
from app.core.models import (
    AnalysisResult,
    PipelineMetrics,
    PipelineRationale,
)
from app.core.session_window import compute_session_window
from app.db.database import SessionLocal
from app.db.repository import SentimentRepository
from app.services.job_manager import JobManager


def _parse_sse_events(text: str) -> list[tuple[str, str]]:
    """Parse raw SSE chunks into list of (type, data/comment)."""
    items = []
    lines = text.strip().split("\n")
    current_event = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith(":"):
            items.append(("comment", line[1:].strip()))
        elif line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:") and current_event:
            items.append(("event", f"{current_event}|{line.replace('data:', '').strip()}"))
            current_event = None
    return items


def _make_dummy_result(ticker: str, run_id: str = "dummy-run-id") -> AnalysisResult:
    session = compute_session_window()
    return AnalysisResult(
        run_id=run_id,
        ticker=ticker,
        company_name=f"{ticker} Corp",
        asset_type=AssetType.EQUITY,
        session=session,
        decision=DecisionVerdict.HOLD,
        decision_confidence=0.5,
        sentiment_score=0.1,
        evidence_quality=0.8,
        disclaimer="For research purposes only.",
        rationale=PipelineRationale(summary="Dummy rationale"),
        metrics=PipelineMetrics(),
        articles=[],
        pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY,
        config_version="test-1.0",
    )


@pytest.mark.asyncio
async def test_job_manager_two_identical_submissions_same_job_id(db_session):
    """Two identical submissions with same cache key return the identical job_id with coalesced=True."""
    jm = JobManager()
    cache_key = "aapl_bucket_1"

    # Slow down pipeline so both requests arrive while job is in-flight
    async def slow_pipeline(*args, **kwargs):
        await asyncio.sleep(0.2)
        return _make_dummy_result("AAPL")

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=slow_pipeline):
        job1_id, coalesced1, max_wait1 = await jm.submit("AAPL", cache_key=cache_key)
        assert coalesced1 is False
        assert max_wait1 > 0

        job2_id, coalesced2, max_wait2 = await jm.submit("AAPL", cache_key=cache_key)
        assert coalesced2 is True
        assert job2_id == job1_id

        # Different cache key returns distinct job
        job3_id, coalesced3, _ = await jm.submit("MSFT", cache_key="msft_bucket_1")
        assert coalesced3 is False
        assert job3_id != job1_id

        await jm.drain()


@pytest.mark.asyncio
async def test_job_manager_concurrency_limit_sequential_execution(db_session):
    """A concurrency limit of 1 runs 3 jobs sequentially while queued jobs reflect position."""
    jm = JobManager(max_concurrent=1)
    execution_order = []
    concurrency_peaks = []
    active = 0

    async def tracking_pipeline(ticker, *args, **kwargs):
        nonlocal active
        active += 1
        concurrency_peaks.append(active)
        execution_order.append(f"start_{ticker}")
        await asyncio.sleep(0.08)
        execution_order.append(f"end_{ticker}")
        active -= 1
        return _make_dummy_result(ticker)

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=tracking_pipeline):
        j1, _, _ = await jm.submit("JOB1", cache_key="k1")
        j2, _, _ = await jm.submit("JOB2", cache_key="k2")
        j3, _, _ = await jm.submit("JOB3", cache_key="k3")

        await jm.drain()

    # Peak concurrency must never exceed max_concurrent (1)
    assert max(concurrency_peaks) == 1
    # All 3 completed sequentially
    assert execution_order == ["start_JOB1", "end_JOB1", "start_JOB2", "end_JOB2", "start_JOB3", "end_JOB3"]

    # In DB, all 3 must be COMPLETED
    db = SessionLocal()
    try:
        assert SentimentRepository.get_job(db, j1).status == JobStatus.COMPLETED.value
        assert SentimentRepository.get_job(db, j2).status == JobStatus.COMPLETED.value
        assert SentimentRepository.get_job(db, j3).status == JobStatus.COMPLETED.value
    finally:
        db.close()


@pytest.mark.asyncio
async def test_job_manager_queue_timeout_fails_job(db_session):
    """Job waiting longer than queue_timeout_seconds fails with QUEUE_TIMEOUT."""
    jm = JobManager(max_concurrent=1, queue_timeout_seconds=0.1)

    async def blocking_pipeline(*args, **kwargs):
        await asyncio.sleep(0.3)
        return _make_dummy_result("SLOW")

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=blocking_pipeline):
        j1, _, _ = await jm.submit("JOB1", cache_key="k1")
        # j2 will wait for j1, exceeding 0.1s queue timeout
        j2, _, _ = await jm.submit("JOB2", cache_key="k2")

        await jm.drain()

    db = SessionLocal()
    try:
        job2 = SentimentRepository.get_job(db, j2)
        assert job2.status == JobStatus.FAILED.value
        assert "timed out" in job2.error_message.lower()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_job_manager_pipeline_timeout_fails_job(db_session):
    """Pipeline execution exceeding pipeline_timeout_seconds fails with PIPELINE_TIMEOUT."""
    jm = JobManager(pipeline_timeout_seconds=0.1)

    async def hanging_pipeline(*args, **kwargs):
        await asyncio.sleep(0.4)
        return _make_dummy_result("HANG")

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=hanging_pipeline):
        job_id, _, _ = await jm.submit("HANG", cache_key="k_hang")
        await jm.drain()

    db = SessionLocal()
    try:
        job = SentimentRepository.get_job(db, job_id)
        assert job.status == JobStatus.FAILED.value
        assert "timed out" in job.error_message.lower()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_job_manager_shutdown_marks_running_jobs_cancelled(db_session):
    """Shutdown cancels active tasks and marks jobs CANCELLED in database."""
    jm = JobManager(max_concurrent=2)

    async def infinite_pipeline(*args, **kwargs):
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            raise
        return _make_dummy_result("INF")

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=infinite_pipeline):
        j1, _, _ = await jm.submit("JOB1", cache_key="k1")
        j2, _, _ = await jm.submit("JOB2", cache_key="k2")
        await asyncio.sleep(0.05)  # allow tasks to start running

        # Invoke shutdown
        await jm.shutdown(timeout=1.0)

    db = SessionLocal()
    try:
        job1 = SentimentRepository.get_job(db, j1)
        job2 = SentimentRepository.get_job(db, j2)
        assert job1.status == JobStatus.CANCELLED.value
        assert job2.status == JobStatus.CANCELLED.value
    finally:
        db.close()


@pytest.mark.asyncio
async def test_job_manager_sse_heartbeat_and_event_order(db_session):
    """SSE stream delivers heartbeat comment (: ping) and events in strict order."""
    jm = JobManager(heartbeat_seconds=0.04)

    async def multistage_pipeline(on_progress, *args, **kwargs):
        await asyncio.sleep(0.02)
        await on_progress(PipelineStage.INGESTING_NEWS, 0.25, "Ingesting...")
        # Pause to let heartbeat fire
        await asyncio.sleep(0.09)
        await on_progress(PipelineStage.FINBERT_SCORING, 0.65, "Scoring...")
        await asyncio.sleep(0.02)
        return _make_dummy_result("HEARTBEAT", run_id="hb-run-123")

    mock_request = MagicMock(spec=Request)
    mock_request.is_disconnected = AsyncMock(return_value=False)

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=multistage_pipeline):
        job_id, _, _ = await jm.submit("HEARTBEAT", cache_key="k_hb")

        collected_chunks = []
        async for chunk in jm.stream_events(job_id, mock_request):
            collected_chunks.append(chunk)

        await jm.drain()

    full_stream = "".join(collected_chunks)
    parsed = _parse_sse_events(full_stream)

    # 1. Heartbeat comment must be present
    comments = [item for item in parsed if item[0] == "comment"]
    assert len(comments) >= 1
    assert any(c[1] == "ping" for c in comments)

    # 2. Events must be in chronological progression
    events = [item[1] for item in parsed if item[0] == "event"]
    assert len(events) >= 3

    # Progress events first
    assert events[0].startswith(f"{SSE_EVENT_PROGRESS}|")
    # Last event must be completed
    assert events[-1].startswith(f"{SSE_EVENT_COMPLETED}|")
    assert "hb-run-123" in events[-1]


@pytest.mark.asyncio
async def test_job_manager_sse_client_disconnect_stops_stream(db_session):
    """Client disconnect cleanly terminates SSE stream without lingering."""
    jm = JobManager(heartbeat_seconds=0.05)

    async def slow_pipeline(*args, **kwargs):
        await asyncio.sleep(1.0)
        return _make_dummy_result("DISC")

    # Simulate disconnect after 2 checks
    disconnect_calls = 0

    async def mock_is_disconnected():
        nonlocal disconnect_calls
        disconnect_calls += 1
        return disconnect_calls >= 2

    mock_request = MagicMock(spec=Request)
    mock_request.is_disconnected = mock_is_disconnected

    with patch("app.services.orchestrator.AnalysisOrchestrator.run_pipeline", side_effect=slow_pipeline):
        job_id, _, _ = await jm.submit("DISC", cache_key="k_disc")

        chunks = []
        async for chunk in jm.stream_events(job_id, mock_request):
            chunks.append(chunk)

        await jm.shutdown()

    # Stream stopped prematurely due to disconnect
    assert len(chunks) < 10


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)
