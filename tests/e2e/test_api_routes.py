import pytest
from unittest.mock import patch
from app.core.models import Asset
from app.core.enums import AssetType
from app.config import settings


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
    assert "database_status" in data
    assert "finbert_status" in data


@pytest.mark.asyncio
async def test_analyze_invalid_ticker(async_client):
    response = await async_client.post("/api/v1/analyze", json={"ticker": "TOOLONGTICKERNAME"})
    assert response.status_code == 422
    data = response.json()
    assert "Invalid ticker" in data.get("detail", "") or "Invalid ticker" in data.get("message", "")


@pytest.mark.asyncio
async def test_analyze_supported_forex(async_client, sample_aapl_articles):
    mock_asset = Asset(
        ticker="EUR/USD",
        company_name="Euro / US Dollar",
        exchange="CCY",
        sector="Financials",
        asset_type=AssetType.FOREX,
        is_active=True,
        yf_symbol="EURUSD=X",
    )
    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=(sample_aapl_articles, {"forex_direct_feeds": {"status": "SUCCESS"}})):
        response = await async_client.post("/api/v1/analyze", json={"ticker": "EUR/USD", "force_refresh": True})
        assert response.status_code in [200, 202]



@pytest.mark.asyncio
async def test_analyze_creates_job_and_polls(async_client, sample_aapl_articles):
    mock_asset = Asset(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=(sample_aapl_articles, {"yfinance": {"status": "SUCCESS"}})):

        # Post analysis request
        response = await async_client.post("/api/v1/analyze", json={"ticker": "AAPL", "force_refresh": True})
        assert response.status_code in [200, 202]
        data = response.json()

        if response.status_code == 202:
            job_id = data["job_id"]
            assert data["ticker"] == "AAPL"
            assert f"/api/v1/jobs/{job_id}" in data["poll_url"]

            # Poll job status
            poll_resp = await async_client.get(f"/api/v1/jobs/{job_id}")
            assert poll_resp.status_code == 200
            poll_data = poll_resp.json()
            assert poll_data["job_id"] == job_id
            assert poll_data["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_history_endpoint(async_client):
    response = await async_client.get("/api/v1/history?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_job_not_found(async_client):
    response = await async_client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_jobs_rate_limiting(async_client):
    """Verify F-15: /jobs/{id} endpoint enforces rate limiting."""
    from app.utils.rate_limiter import rate_limiter
    rate_limiter.reset()

    # Rapidly send requests up to rate limit
    for _ in range(settings.RATE_LIMIT_JOBS_PER_MINUTE):
        resp = await async_client.get("/api/v1/jobs/test-rate-limit-id")
        assert resp.status_code in [404, 200]

    # The 61st request in the same minute window must be rejected with 429
    resp_limit = await async_client.get("/api/v1/jobs/test-rate-limit-id")
    assert resp_limit.status_code == 429
    rate_limiter.reset()
