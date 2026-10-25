"""Integration tests for DataStatus, HOLD reasons, and short cache TTLs (P2.6, M12, D6)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.enums import AssetType, DataStatus, DecisionVerdict, HoldReason, ProviderType
from app.core.models import Asset, IngestedArticle
from app.core.session_window import compute_session_bucket, compute_session_window
from app.db.repository import SentimentRepository
from app.services.orchestrator import AnalysisOrchestrator


@pytest.mark.asyncio
async def test_irrelevant_only_news_produces_no_relevant_news_and_skips_finbert_llm(db_session):
    """
    When articles arrive in-window but 0 survive entity relevance, orchestrator sets:
    - data_status = NO_RELEVANT_NEWS
    - decision = HOLD
    - decision_confidence = 0.0
    - hold_reason = NO_NEWS
    - FinBERT scoring and LLM synthesis are completely skipped.
    """
    now = compute_session_window().window_end_utc
    mock_asset = Asset(
        ticker="AMD",
        company_name="Advanced Micro Devices, Inc.",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
    )

    # Article has nothing to do with AMD (irrelevant company and keywords)
    art_irrelevant = IngestedArticle(
        article_id="art_irr_1",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Generic News",
        canonical_url="https://example.com/irr1",
        title="Wheat harvest outlook remains strong in Kansas",
        summary="Agriculture commodity production is on track this season.",
        published_at_utc=now - timedelta(hours=2),
        retrieved_at_utc=now,
    )

    mock_finbert = MagicMock()
    mock_finbert.score_articles_async = AsyncMock()

    mock_llm = MagicMock()
    mock_llm.verify_and_synthesize = AsyncMock()

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([art_irrelevant], {"yfinance": {"status": "SUCCESS"}}))), \
         patch("app.services.finbert_service.FinBERTService.get_instance", return_value=mock_finbert), \
         patch("app.services.llm_service.LLMService", return_value=mock_llm):

        result = await AnalysisOrchestrator.run_pipeline(
            ticker="AMD",
            db=db_session,
            force_refresh=True,
            enable_llm=True,
        )

        assert result.decision == DecisionVerdict.HOLD
        assert result.data_status == DataStatus.NO_RELEVANT_NEWS
        assert result.decision_confidence == 0.0
        assert result.hold_reason == HoldReason.NO_NEWS
        assert result.metrics.articles_retained == 0
        assert result.metrics.articles_scored_local == 0
        assert result.metrics.articles_sent_to_llm == 0

        # Verify FinBERT and LLM were never called
        mock_finbert.score_articles_async.assert_not_called()
        mock_llm.verify_and_synthesize.assert_not_called()


@pytest.mark.asyncio
async def test_no_relevant_news_cache_ttl_capped_at_300s(db_session):
    """NO_RELEVANT_NEWS runs expire from cache after 300 seconds regardless of longer session buckets."""
    now = datetime.now(timezone.utc)
    mock_asset = Asset(
        ticker="AMD",
        company_name="Advanced Micro Devices, Inc.",
        exchange="NASDAQ",
        asset_type=AssetType.EQUITY,
    )
    art_irrelevant = IngestedArticle(
        article_id="art_irr_2",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Generic News",
        canonical_url="https://example.com/irr2",
        title="Local library hosts summer reading program",
        summary="Community events in the local library.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([art_irrelevant], {"yfinance": {"status": "SUCCESS"}}))):

        result = await AnalysisOrchestrator.run_pipeline("AMD", db_session, force_refresh=True, enable_llm=False)
        assert result.data_status == DataStatus.NO_RELEVANT_NEWS

        session = compute_session_window()
        session_bucket, _ = compute_session_bucket(session)
        cache_key = AnalysisOrchestrator.compute_cache_key("AMD", session_bucket, "yfinance_rss", False)

        # Within 300 seconds (e.g. 100s age), cache hit
        cached_recent = SentimentRepository.get_cached_run(db_session, cache_key, max_age_seconds=900)
        assert cached_recent is not None
        assert cached_recent.data_status == DataStatus.NO_RELEVANT_NEWS

        # Simulate age of 301 seconds by backdating created_at in the DB
        from app.db.models import AnalysisRunDB
        run_record = db_session.query(AnalysisRunDB).filter(AnalysisRunDB.id == result.run_id).first()
        run_record.created_at = now - timedelta(seconds=305)
        db_session.commit()

        # Even though max_age_seconds is 900, the effective TTL is min(900, 300) = 300, so it's a MISS
        cached_expired = SentimentRepository.get_cached_run(db_session, cache_key, max_age_seconds=900)
        assert cached_expired is None


@pytest.mark.asyncio
async def test_degraded_status_when_all_rss_fail(db_session):
    """When all RSS feeds fail, data_status is DEGRADED and is_cacheable is False."""
    now = compute_session_window().window_end_utc
    mock_asset = Asset(ticker="AAPL", company_name="Apple Inc.", exchange="NASDAQ")
    art1 = IngestedArticle(
        article_id="art_yf_only",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/yf",
        title="Apple launches updated Mac computers",
        summary="Apple introduced new hardware products.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    degraded_outcomes = {
        "yfinance": {"status": "SUCCESS", "count": 1},
        "rss_reuters": {"status": "FAILED", "error": "HTTP 500"},
        "rss_google_news_general": {"status": "FAILED", "error": "Timeout"},
        "google_news_rss_total": {"status": "FAILED", "count": 0},
    }

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([art1], degraded_outcomes))):

        result = await AnalysisOrchestrator.run_pipeline("AAPL", db_session, force_refresh=True, enable_llm=False)
        assert result.data_status == DataStatus.DEGRADED

        # Stored in DB
        persisted = SentimentRepository.get_analysis_run(db_session, result.run_id)
        assert persisted is not None
        assert persisted.data_status == DataStatus.DEGRADED

        # Not returned from cache
        session = compute_session_window()
        session_bucket, _ = compute_session_bucket(session)
        cache_key = AnalysisOrchestrator.compute_cache_key("AAPL", session_bucket, "yfinance_rss", False)
        cached = SentimentRepository.get_cached_run(db_session, cache_key, max_age_seconds=900)
        assert cached is None


@pytest.mark.asyncio
async def test_total_provider_outage_produces_persisted_degraded_run_and_not_cached(db_session):
    """When Yahoo and all RSS feeds fail, orchestrator emits a persisted DEGRADED run with is_cacheable=False."""
    mock_asset = Asset(ticker="TSLA", company_name="Tesla, Inc.", exchange="NASDAQ")
    all_failed_outcomes = {
        "yfinance": {"status": "FAILED", "error": "HTTP 503 Service Unavailable"},
        "rss_reuters": {"status": "FAILED", "error": "Connection reset"},
        "rss_google_news_general": {"status": "FAILED", "error": "HTTP 429 Too Many Requests"},
        "google_news_rss_total": {"status": "FAILED", "error": "Timeout"},
    }

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([], all_failed_outcomes))):

        result = await AnalysisOrchestrator.run_pipeline("TSLA", db_session, force_refresh=True, enable_llm=False)
        assert result.data_status == DataStatus.DEGRADED
        assert result.decision == DecisionVerdict.HOLD
        assert result.hold_reason == HoldReason.NO_NEWS
        assert result.decision_confidence == 0.0
        assert any("All external news providers failed to respond" in w for w in result.warnings)

        # Assert persisted run status in DB
        persisted = SentimentRepository.get_analysis_run(db_session, result.run_id)
        assert persisted is not None
        assert persisted.data_status == DataStatus.DEGRADED

        from app.db.models import AnalysisRunDB
        db_run = db_session.query(AnalysisRunDB).filter(AnalysisRunDB.id == result.run_id).first()
        assert db_run is not None
        assert db_run.is_cacheable is False
        assert db_run.data_status == "DEGRADED"

        # Assert retrievability via repository
        assert persisted.ticker == "TSLA"
        assert persisted.decision == DecisionVerdict.HOLD

        # Assert cache exclusion
        session = compute_session_window()
        session_bucket, _ = compute_session_bucket(session)
        cache_key = AnalysisOrchestrator.compute_cache_key("TSLA", session_bucket, "yfinance_rss", False)
        cached = SentimentRepository.get_cached_run(db_session, cache_key, max_age_seconds=900)
        assert cached is None
