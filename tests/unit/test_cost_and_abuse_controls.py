import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.config import settings
from app.core.exceptions import InvalidTickerException
from app.services.llm_service import LLMService
from app.services.ticker_service import TickerService


@pytest.mark.asyncio
async def test_api_key_required_when_configured(async_client: AsyncClient):
    """Verify missing or wrong X-API-Key returns 401 when API_KEY is set."""
    from app.core.enums import AssetType
    from app.core.models import Asset

    dummy_asset = Asset(ticker="AAPL", company_name="Apple Inc.", exchange="NASDAQ", asset_type=AssetType.EQUITY, yf_symbol="AAPL")
    with patch("app.services.ticker_service.TickerService.resolve_ticker_async", new_callable=AsyncMock, return_value=dummy_asset):
        with patch("app.services.job_manager.JobManager.submit", new_callable=AsyncMock, return_value=("mock-job-id", False, 150)):
            with patch.object(settings, "API_KEY", "super-secret-key"):
                # 1. Missing header -> 401
                res = await async_client.post("/api/v1/analyze", json={"ticker": "AAPL"})
                assert res.status_code == 401
                data = res.json()
                assert data["error"] == "UnauthorizedException"
                assert "Invalid or missing API key" in data["message"]

                # 2. Invalid header -> 401
                res = await async_client.post(
                    "/api/v1/analyze",
                    json={"ticker": "AAPL"},
                    headers={"X-API-Key": "wrong-key"},
                )
                assert res.status_code == 401
                assert res.json()["error"] == "UnauthorizedException"

                # 3. Valid header -> succeeds past auth gate (200 or 202)
                res = await async_client.post(
                    "/api/v1/analyze",
                    json={"ticker": "AAPL"},
                    headers={"X-API-Key": "super-secret-key"},
                )
                assert res.status_code in (200, 202)


@pytest.mark.asyncio
async def test_public_history_gating(async_client: AsyncClient):
    """Verify PUBLIC_HISTORY=false requires API_KEY for /history and /analysis/{id}."""
    with patch.object(settings, "API_KEY", "secret-123"):
        # When PUBLIC_HISTORY is False
        with patch.object(settings, "PUBLIC_HISTORY", False):
            # Missing key -> 401
            res_hist = await async_client.get("/api/v1/history")
            assert res_hist.status_code == 401

            fake_id = str(uuid.uuid4())
            res_analysis = await async_client.get(f"/api/v1/analysis/{fake_id}")
            assert res_analysis.status_code == 401

            # Valid key -> passes auth (200 for history, 404 for non-existent analysis)
            res_hist_ok = await async_client.get(
                "/api/v1/history", headers={"X-API-Key": "secret-123"}
            )
            assert res_hist_ok.status_code == 200

            res_analysis_ok = await async_client.get(
                f"/api/v1/analysis/{fake_id}", headers={"X-API-Key": "secret-123"}
            )
            assert res_analysis_ok.status_code == 404  # Not 401

        # When PUBLIC_HISTORY is True (default) -> unrestricted
        with patch.object(settings, "PUBLIC_HISTORY", True):
            res_hist_public = await async_client.get("/api/v1/history")
            assert res_hist_public.status_code == 200


@pytest.mark.asyncio
async def test_exhausted_daily_llm_budget_skips_synthesis():
    """Verify when today's UTC spend >= LLM_DAILY_BUDGET_USD, LLM synthesis is skipped."""
    service = LLMService(client=AsyncMock())
    with patch.object(service, "get_today_utc_spend", AsyncMock(return_value=1.50)):
        with patch.object(settings, "LLM_DAILY_BUDGET_USD", 1.00):
            _, facts, summary, telemetry = await service.verify_and_synthesize(
                "AAPL", "Apple Inc.", []
            )
            assert telemetry["status"] == "SKIPPED"
            # If no candidates, NO_DIRECTIONAL_CANDIDATES or DAILY_BUDGET_EXCEEDED
            # Let's test with directional candidates present


@pytest.mark.asyncio
async def test_exhausted_budget_with_candidates_skips_llm():
    """Verify DAILY_BUDGET_EXCEEDED is returned when eligible candidates exist."""
    from datetime import datetime, timezone

    from app.core.enums import ProviderType
    from app.core.models import ScoredArticle

    now = datetime.now(timezone.utc)
    art = ScoredArticle(
        article_id="art_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_publisher="Reuters",
        canonical_url="https://example.com/1",
        title="Apple reports strong quarterly earnings beat",
        lead_text="Apple reports strong quarterly earnings beat.",
        published_at_utc=now,
        finbert_positive=0.9,
        finbert_negative=0.05,
        finbert_neutral=0.05,
        finbert_directional_score=0.85,
        finbert_confidence=0.9,
    )

    mock_client = AsyncMock()
    service = LLMService(client=mock_client)
    with patch.object(service, "get_today_utc_spend", AsyncMock(return_value=1.20)):
        with patch.object(settings, "LLM_DAILY_BUDGET_USD", 1.00):
            with patch.object(settings, "ENABLE_LLM", True):
                _, facts, summary, telemetry = await service.verify_and_synthesize(
                    "AAPL", "Apple Inc.", [art]
                )
                assert telemetry["status"] == "SKIPPED"
                assert telemetry["reason"] == "DAILY_BUDGET_EXCEEDED"
                assert facts == []
                assert summary == ""
                mock_client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_ticker_max_length_enforcement(async_client: AsyncClient):
    """Verify 21-character ticker is rejected with 422."""
    long_ticker = "A" * 21

    # 1. Pydantic request body validation -> 422
    res = await async_client.post("/api/v1/analyze", json={"ticker": long_ticker})
    assert res.status_code == 422
    data = res.json()
    assert data["error"] == "RequestValidationError"

    # 2. TickerService.normalize_ticker -> InvalidTickerException
    with pytest.raises(InvalidTickerException) as exc_info:
        TickerService.normalize_ticker(long_ticker)
    assert "20 characters" in str(exc_info.value.message)


@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient):
    """Verify security headers are applied to HTTP responses."""
    res = await async_client.get("/api/v1/health")
    assert res.status_code == 200

    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in res.headers
    csp = res.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp


@pytest.mark.asyncio
async def test_cors_credentials_disallowed(async_client: AsyncClient):
    """Verify CORS does not allow credentials."""
    res = await async_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # With allow_credentials=False, Access-Control-Allow-Credentials is not 'true'
    assert res.headers.get("access-control-allow-credentials") != "true"


def test_repository_get_daily_llm_spend(db_session):
    """Verify SentimentRepository.get_daily_llm_spend computes UTC daily spend accurately."""
    from datetime import datetime, timedelta, timezone

    from app.db.models import AnalysisRunDB
    from app.db.repository import SentimentRepository

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # 1. Empty DB -> 0.0
    spend_initial = SentimentRepository.get_daily_llm_spend(db_session)
    assert spend_initial == 0.0

    # 2. Add run for today
    run_today = AnalysisRunDB(
        id=str(uuid.uuid4()),
        ticker="AAPL",
        company_name="Apple Inc.",
        asset_type="EQUITY",
        session_type="REGULAR_HOURS",
        cache_key="ckey_today",
        window_start_utc=now,
        window_end_utc=now,
        run_timestamp_utc=now,
        decision="BUY",
        sentiment_score=0.5,
        decision_confidence=0.8,
        evidence_quality=0.8,
        rationale_summary="Summary",
        pipeline_mode="HYBRID_FINBERT_LLM",
        config_version="v1",
        llm_cost_usd=0.045,
        created_at=now,
    )
    # Add run for yesterday
    run_yesterday = AnalysisRunDB(
        id=str(uuid.uuid4()),
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        asset_type="EQUITY",
        session_type="REGULAR_HOURS",
        cache_key="ckey_yesterday",
        window_start_utc=yesterday,
        window_end_utc=yesterday,
        run_timestamp_utc=yesterday,
        decision="HOLD",
        sentiment_score=0.1,
        decision_confidence=0.5,
        evidence_quality=0.5,
        rationale_summary="Summary",
        pipeline_mode="HYBRID_FINBERT_LLM",
        config_version="v1",
        llm_cost_usd=0.030,
        created_at=yesterday,
    )
    db_session.add(run_today)
    db_session.add(run_yesterday)
    db_session.commit()

    spend_today = SentimentRepository.get_daily_llm_spend(db_session)
    assert abs(spend_today - 0.045) < 1e-5

    spend_yesterday = SentimentRepository.get_daily_llm_spend(db_session, target_date=yesterday)
    assert abs(spend_yesterday - 0.030) < 1e-5


@pytest.mark.asyncio
async def test_llm_service_get_today_utc_spend_live_db(db_session):
    """Verify LLMService.get_today_utc_spend queries DB through worker pool."""
    service = LLMService()
    spend = await service.get_today_utc_spend()
    assert isinstance(spend, float)

