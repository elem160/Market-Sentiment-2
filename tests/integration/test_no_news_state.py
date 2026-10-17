import pytest
from unittest.mock import patch
from app.services.orchestrator import AnalysisOrchestrator
from app.core.models import Asset
from app.core.enums import AssetType, DecisionVerdict
from app.db.repository import SentimentRepository


@pytest.mark.asyncio
async def test_no_current_day_news_returns_clean_hold(db_session):
    """When zero articles pass the session window, pipeline terminates cleanly with low-evidence HOLD."""
    mock_asset = Asset(
        ticker="GOOGL",
        company_name="Alphabet Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=([], {"yfinance": {"status": "SUCCESS", "count": 0}})):

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="GOOGL",
            db=db_session,
            force_refresh=True,
            enable_llm=False,
        )

        assert result.ticker == "GOOGL"
        assert result.decision == DecisionVerdict.HOLD
        assert result.sentiment_score == 0.0
        assert result.decision_confidence == 0.0
        assert result.evidence_quality == 0.0
        assert len(result.articles) == 0
        assert "No verifiable news" in result.rationale.summary
        assert any("No current-day news" in w for w in result.warnings)

        # Ensure run is persisted in database
        saved = SentimentRepository.get_analysis_run(db_session, result.run_id)
        assert saved is not None
        assert saved.decision == DecisionVerdict.HOLD
