import pytest
from unittest.mock import patch
from app.services.orchestrator import AnalysisOrchestrator
from app.core.models import Asset
from app.core.enums import AssetType, DecisionVerdict, PipelineMode
from app.db.repository import SentimentRepository


@pytest.mark.asyncio
async def test_full_pipeline_positive_aapl(db_session, sample_aapl_articles):
    """Test full 6-stage pipeline execution with positive Apple news fixture -> BUY."""
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

        progress_events = []
        async def on_progress(stage, pct, msg):
            progress_events.append((stage, pct, msg))

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="AAPL",
            db=db_session,
            force_refresh=True,
            enable_llm=False,  # Test deterministic classifier-only mode
            on_progress=on_progress,
        )

        assert result.ticker == "AAPL"
        assert result.company_name == "Apple Inc."
        assert result.decision == DecisionVerdict.BUY
        assert result.sentiment_score >= 0.35
        assert result.decision_confidence > 0.0
        assert result.pipeline_mode == PipelineMode.DETERMINISTIC_FINBERT_ONLY
        assert len(result.articles) == 3
        assert len(progress_events) >= 5

        # Verify database persistence
        saved = SentimentRepository.get_analysis_run(db_session, result.run_id)
        assert saved is not None
        assert saved.ticker == "AAPL"
        assert saved.decision == DecisionVerdict.BUY


@pytest.mark.asyncio
async def test_full_pipeline_negative_nvda(db_session, sample_nvda_articles):
    """Test full 6-stage pipeline execution with negative Nvidia news fixture -> SELL."""
    mock_asset = Asset(
        ticker="NVDA",
        company_name="Nvidia Corp.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=(sample_nvda_articles, {"yfinance": {"status": "SUCCESS"}})):

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="NVDA",
            db=db_session,
            force_refresh=True,
            enable_llm=False,
        )

        assert result.ticker == "NVDA"
        assert result.decision == DecisionVerdict.SELL
        assert result.sentiment_score <= -0.35
        assert result.decision_confidence >= 0.40
