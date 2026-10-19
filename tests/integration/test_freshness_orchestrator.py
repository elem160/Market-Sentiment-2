import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from app.core.models import Asset, IngestedArticle
from app.core.enums import AssetType, DecisionVerdict, ProviderType
from app.core.exceptions import NewsUnavailableException
from app.services.orchestrator import AnalysisOrchestrator


@pytest.mark.asyncio
async def test_historical_articles_rejected_producing_no_fresh_news_state(db_session):
    """Regression test for F-01: When all articles are historical (e.g. 2018), orchestrator outputs HOLD and NO_FRESH_NEWS."""
    mock_asset = Asset(
        ticker="BTC-USD",
        company_name="Bitcoin USD",
        exchange="CRYPTO",
        sector="Cryptocurrency",
        asset_type=AssetType.CRYPTO,
        is_active=True,
    )

    # Ingest historical articles (from 2017/2018)
    historical_articles = [
        IngestedArticle(
            article_id="btc_hist_1",
            provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
            source_name="CoinDesk",
            canonical_url="https://example.com/btc/1",
            title="Bitcoin Surges Toward 20000 in Historic 2017 Rally",
            summary="Bull market frenzy in late 2017 pushes crypto prices to record highs.",
            published_at_utc=datetime(2017, 12, 15, 12, 0, tzinfo=timezone.utc),
            retrieved_at_utc=datetime.now(timezone.utc),
            raw_provider_metadata={},
        ),
        IngestedArticle(
            article_id="btc_hist_2",
            provider=ProviderType.YFINANCE,
            source_name="Bloomberg",
            canonical_url="https://example.com/btc/2",
            title="Bitcoin Retreats in 2018 Crypto Winter",
            summary="Regulatory headwinds and exchange reviews slow digital asset investment.",
            published_at_utc=datetime(2018, 6, 20, 10, 0, tzinfo=timezone.utc),
            retrieved_at_utc=datetime.now(timezone.utc),
            raw_provider_metadata={},
        ),
    ]

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=(historical_articles, {"yfinance": {"status": "SUCCESS", "count": 1}, "google_rss": {"status": "SUCCESS", "count": 1}})):

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="BTC-USD",
            db=db_session,
            force_refresh=True,
            enable_llm=False,
        )

        assert result.ticker == "BTC-USD"
        assert result.decision == DecisionVerdict.HOLD
        assert result.sentiment_score == 0.0
        assert result.decision_confidence == 0.0
        assert result.data_status == "NO_FRESH_NEWS"
        # Scored retained articles is 0
        assert len([a for a in result.articles if a.exclusion_reason is None]) == 0
        # Excluded sample articles are populated for UI transparency
        assert len([a for a in result.articles if a.exclusion_reason is not None]) == 2
        assert result.metrics.excluded_out_of_window == 2
        assert result.metrics.excluded_missing_timestamp == 0
        assert "No articles published inside the current session window" in result.rationale.summary


@pytest.mark.asyncio
async def test_empty_feed_with_success_status_does_not_trigger_503(db_session):
    """A well-formed feed returning 0 entries has SUCCESS status (count 0) and does not raise NewsUnavailableException."""
    mock_asset = Asset(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=([], {"yfinance": {"status": "SUCCESS", "count": 0}, "google_rss": {"status": "SUCCESS", "count": 0}})):

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="AAPL",
            db=db_session,
            force_refresh=True,
            enable_llm=False,
        )

        assert result.decision == DecisionVerdict.HOLD
        assert result.data_status == "NO_FRESH_NEWS"


@pytest.mark.asyncio
async def test_total_provider_outage_raises_news_unavailable(db_session):
    """When all news providers fail, orchestrator raises NewsUnavailableException (503)."""
    mock_asset = Asset(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=([], {"yfinance": {"status": "FAILED", "error": "Timeout"}, "google_rss": {"status": "FAILED", "error": "HTTP 500"}})):

        with pytest.raises(NewsUnavailableException):
            await AnalysisOrchestrator.run_pipeline(
                ticker="AAPL",
                db=db_session,
                force_refresh=True,
                enable_llm=False,
            )
