import uuid
from unittest.mock import patch
import pytest
from httpx import AsyncClient
from app.services.finbert_service import FinBERTService
from app.utils.rate_limiter import rate_limiter


@pytest.mark.asyncio
async def test_404_job_not_found_unified_shape(async_client: AsyncClient):
    """Verify 404 returns unified error shape {error, message, details} for unknown job."""
    non_existent_id = str(uuid.uuid4())
    res = await async_client.get(f"/api/v1/jobs/{non_existent_id}")
    assert res.status_code == 404
    data = res.json()
    assert data["error"] == "JobNotFoundException"
    assert non_existent_id in data["message"]
    assert data["details"] == {"job_id": non_existent_id}


@pytest.mark.asyncio
async def test_404_analysis_run_not_found_unified_shape(async_client: AsyncClient):
    """Verify 404 returns unified error shape {error, message, details} for unknown analysis run."""
    non_existent_run = str(uuid.uuid4())
    res = await async_client.get(f"/api/v1/analysis/{non_existent_run}")
    assert res.status_code == 404
    data = res.json()
    assert data["error"] == "AnalysisRunNotFoundException"
    assert non_existent_run in data["message"]
    assert data["details"] == {"run_id": non_existent_run}


@pytest.mark.asyncio
async def test_422_request_validation_error_unified_shape(async_client: AsyncClient):
    """Verify 422 RequestValidationError returns unified error shape with field errors."""
    res = await async_client.post("/api/v1/analyze", json={})
    assert res.status_code == 422
    data = res.json()
    assert data["error"] == "RequestValidationError"
    assert "details" in data
    assert "errors" in data["details"]
    assert len(data["details"]["errors"]) > 0


@pytest.mark.asyncio
async def test_422_domain_validation_error_unified_shape(async_client: AsyncClient):
    """Verify 422 domain validation returns unified error shape."""
    res = await async_client.post("/api/v1/analyze", json={"ticker": "INVALID$$$"})
    assert res.status_code == 422
    data = res.json()
    assert data["error"] in ("InvalidTickerException", "UnsupportedAssetException")
    assert "message" in data
    assert "details" in data


@pytest.mark.asyncio
async def test_429_rate_limit_exceeded_with_retry_after(async_client: AsyncClient):
    """Verify 429 returns unified shape and Retry-After header."""
    from app.config import settings

    rate_limiter.reset()
    limit = settings.RATE_LIMIT_JOBS_PER_MINUTE
    for _ in range(limit):
        rate_limiter.check("jobs", "testclient", max_requests=limit, window_seconds=60)
        rate_limiter.check("jobs", "127.0.0.1", max_requests=limit, window_seconds=60)
    
    res = await async_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert res.status_code == 429
    assert "Retry-After" in res.headers
    retry_after = int(res.headers["Retry-After"])
    assert retry_after >= 1
    data = res.json()
    assert data["error"] == "RateLimitExceededException"
    assert "details" in data
    assert data["details"].get("retry_after_seconds") == retry_after


@pytest.mark.asyncio
async def test_500_internal_server_error_unified_shape():
    """Verify unhandled 500 returns unified shape with error_id and generic message."""
    from httpx import ASGITransport
    from app.main import app
    client = AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver")
    async with client:
        with patch("app.db.repository.SentimentRepository.get_job", side_effect=RuntimeError("Boom")):
            res = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
            assert res.status_code == 500
            data = res.json()
            assert data["error"] == "InternalServerError"
            assert data["message"] == "An internal server error occurred."
            assert "details" in data
            assert "error_id" in data["details"]
            assert len(data["details"]["error_id"]) > 0


@pytest.mark.asyncio
async def test_health_check_healthy(async_client: AsyncClient):
    """Verify /health returns 200 UP and truthful finbert_status."""
    res = await async_client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UP"
    assert data["database_status"] == "HEALTHY"
    assert data["finbert_status"] == "LOADED"


@pytest.mark.asyncio
async def test_health_check_not_loaded():
    """Verify FinBERTService reports NOT_LOADED when uninitialized."""
    from app.services.scoring import FinBERTScorer, set_default_scorer
    scorer = FinBERTScorer()
    set_default_scorer(scorer)
    assert FinBERTService.get_status() == "NOT_LOADED"


@pytest.mark.asyncio
async def test_health_check_database_failure(async_client: AsyncClient):
    """Verify /health returns 503 DEGRADED with no raw exception leaks when DB fails."""
    with patch("app.db.repository.SentimentRepository.get_recent_runs", side_effect=Exception("Raw DB secret error!")):
        res = await async_client.get("/api/v1/health")
        assert res.status_code == 503
        data = res.json()
        assert data["status"] == "DEGRADED"
        assert data["database_status"] == "UNHEALTHY"
        # Must not leak the raw exception text
        assert "Raw DB secret error!" not in str(data)
