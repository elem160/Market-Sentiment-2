"""Verify Server-Sent Events (SSE) contract, event ordering, and payload validation (C1)."""
import asyncio
import json
import pytest

from app.api.schemas import (
    SSE_EVENT_COMPLETED,
    SSE_EVENT_FAILED,
    SSE_EVENT_PROGRESS,
    JobCompletedEvent,
    JobFailedEvent,
    JobProgressEvent,
)
from app.core.enums import JobStatus, PipelineStage
from app.db.database import SessionLocal
from app.db.repository import SentimentRepository


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse raw SSE chunk into list of (event_name, data_dict)."""
    events = []
    current_event = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:") and current_event:
            data_json = json.loads(line.replace("data:", "").strip())
            events.append((current_event, data_json))
            current_event = None
    return events


@pytest.mark.asyncio
async def test_sse_unknown_job_returns_404(async_client):
    """An unknown job returns 404 before opening the stream (C1)."""
    response = await async_client.get("/api/v1/jobs/nonexistent-job-uuid/events")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_sse_successful_job_flow(async_client, db_session):
    """A running job emits valid JobProgressEvents followed by JobCompletedEvent."""
    job_id = "test-sse-success-job"
    SentimentRepository.create_job(db_session, job_id, "AAPL")

    async def simulate_job_lifecycle():
        await asyncio.sleep(0.05)
        db = SessionLocal()
        try:
            SentimentRepository.update_job_stage(
                db, job_id, PipelineStage.INGESTING_NEWS, 0.25, "Fetching articles..."
            )
            await asyncio.sleep(0.05)
            SentimentRepository.update_job_stage(
                db, job_id, PipelineStage.FINBERT_SCORING, 0.65, "Scoring FinBERT..."
            )
            await asyncio.sleep(0.05)
            SentimentRepository.complete_job(db, job_id, "mock-run-id-123")
        finally:
            db.close()

    lifecycle_task = asyncio.create_task(simulate_job_lifecycle())

    collected_chunks = []
    async with async_client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        async for chunk in response.aiter_text():
            collected_chunks.append(chunk)

    await lifecycle_task

    raw_stream = "".join(collected_chunks)
    parsed_events = _parse_sse_events(raw_stream)

    assert len(parsed_events) >= 2, f"Expected progress and completion events, got: {parsed_events}"

    # Verify progress events
    progress_events = [e for e in parsed_events if e[0] == SSE_EVENT_PROGRESS]
    assert len(progress_events) >= 1
    for _, payload in progress_events:
        model = JobProgressEvent(**payload)
        assert model.job_id == job_id
        assert model.ticker == "AAPL"
        assert model.status in (JobStatus.QUEUED, JobStatus.PROCESSING)
        assert 0.0 <= model.progress_pct <= 1.0

    # Verify terminal completed event
    last_event_name, last_payload = parsed_events[-1]
    assert last_event_name == SSE_EVENT_COMPLETED
    completed_model = JobCompletedEvent(**last_payload)
    assert completed_model.job_id == job_id
    assert completed_model.status == "COMPLETED"
    assert completed_model.run_id == "mock-run-id-123"
    assert completed_model.message == "Analysis complete."


@pytest.mark.asyncio
async def test_sse_failing_job_flow(async_client, db_session):
    """A failing job emits JobFailedEvent with error_message."""
    job_id = "test-sse-fail-job"
    SentimentRepository.create_job(db_session, job_id, "TSLA")

    async def simulate_failure():
        await asyncio.sleep(0.05)
        db = SessionLocal()
        try:
            SentimentRepository.fail_job(db, job_id, "Simulated upstream provider outage")
        finally:
            db.close()

    failure_task = asyncio.create_task(simulate_failure())

    collected_chunks = []
    async with async_client.stream("GET", f"/api/v1/jobs/{job_id}/events") as response:
        assert response.status_code == 200
        async for chunk in response.aiter_text():
            collected_chunks.append(chunk)

    await failure_task

    raw_stream = "".join(collected_chunks)
    parsed_events = _parse_sse_events(raw_stream)

    assert len(parsed_events) >= 1
    last_event_name, last_payload = parsed_events[-1]
    assert last_event_name == SSE_EVENT_FAILED
    failed_model = JobFailedEvent(**last_payload)
    assert failed_model.job_id == job_id
    assert failed_model.status == "FAILED"
    assert failed_model.error_code == "JOB_FAILED"
    assert "Simulated upstream provider outage" in failed_model.error_message
