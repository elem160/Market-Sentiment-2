from unittest.mock import patch

import pytest

from app.core.enums import AssetType
from app.core.models import Asset
from app.services.orchestrator import AnalysisOrchestrator


def _sanitize_for_snapshot(result_dict: dict) -> dict:
    """Remove nondeterministic runtime fields (IDs, latencies) for golden comparison."""
    sanitized = dict(result_dict)
    sanitized.pop("run_id", None)
    sanitized.pop("created_at", None)
    
    if "metrics" in sanitized and isinstance(sanitized["metrics"], dict):
        m = dict(sanitized["metrics"])
        m.pop("stage_latencies", None)
        m.pop("total_latency_ms", None)
        sanitized["metrics"] = m
        
    if "session" in sanitized and isinstance(sanitized["session"], dict):
        s = dict(sanitized["session"])
        sanitized["session"] = s

    if "articles" in sanitized and isinstance(sanitized["articles"], list):
        clean_articles = []
        for art in sanitized["articles"]:
            a = dict(art)
            a.pop("retrieved_at_utc", None)
            clean_articles.append(a)
        sanitized["articles"] = clean_articles

    return sanitized


@pytest.mark.asyncio
async def test_orchestrator_golden_snapshot(db_session, sample_aapl_articles):
    """Guards against regressions during orchestrator refactoring (Task P4.1)."""
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

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="AAPL",
            db=db_session,
            force_refresh=True,
            enable_llm=False,
        )

    dumped = result.model_dump(mode="json")
    sanitized = _sanitize_for_snapshot(dumped)

    # High-level contract invariants
    assert sanitized["ticker"] == "AAPL"
    assert sanitized["company_name"] == "Apple Inc."
    assert sanitized["asset_type"] == "EQUITY"
    assert sanitized["decision"] == "BUY"
    assert sanitized["decision_confidence"] == pytest.approx(0.5334, rel=1e-3)
    assert sanitized["sentiment_score"] == pytest.approx(0.8, rel=1e-3)
    assert sanitized["data_status"] == "OK"
    assert sanitized["pipeline_mode"] == "DETERMINISTIC_FINBERT_ONLY"
    assert sanitized["hold_reason"] is None
    assert len(sanitized["articles"]) == 3
    assert len(sanitized["provider_outcomes"]) == 1

    # Exact golden metrics invariant
    metrics = sanitized["metrics"]
    assert metrics["articles_ingested"] == 3
    assert metrics["articles_retained"] == 3
    assert metrics["articles_scored_local"] == 3
    assert metrics["articles_deduplicated"] == 0
    assert metrics["articles_excluded_total"] == 0
    assert metrics["distinct_publishers"] == 3
    assert metrics["distinct_clusters"] == 3
    assert metrics["publishers_positive"] == 2
    assert metrics["publishers_negative"] == 0
    assert metrics["supporting_publishers"] == 2
    assert metrics["prompt_tokens"] == 0
    assert metrics["completion_tokens"] == 0
    assert metrics["estimated_cost_usd"] == 0.0

    # Articles verification
    for art in sanitized["articles"]:
        assert art["exclusion_reason"] is None
        assert art["finbert_directional_score"] >= 0.0
        assert art["canonical_publisher"] in {"Reuters", "Bloomberg", "Wall Street Journal", "CNBC"}

    # Rationale verification
    assert "BUY: Positive catalyst momentum" in sanitized["rationale"]["summary"]
    assert len(sanitized["rationale"]["inferences"]) >= 3


@pytest.mark.asyncio
async def test_orchestrator_golden_snapshot_no_fresh_news(db_session):
    """Guards against regressions in NO_FRESH_NEWS empty-window branch."""
    mock_asset = Asset(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=([], {"yfinance": {"status": "SUCCESS"}})):

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="AAPL",
            db=db_session,
            force_refresh=True,
            enable_llm=False,
        )

    dumped = result.model_dump(mode="json")
    sanitized = _sanitize_for_snapshot(dumped)

    assert sanitized["ticker"] == "AAPL"
    assert sanitized["decision"] == "HOLD"
    assert sanitized["data_status"] == "NO_FRESH_NEWS"
    assert sanitized["hold_reason"] == "NO_NEWS"
    assert sanitized["sentiment_score"] == 0.0
    assert sanitized["decision_confidence"] == 0.0
    assert sanitized["metrics"]["articles_ingested"] == 0
    assert sanitized["metrics"]["articles_retained"] == 0

