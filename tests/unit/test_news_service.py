import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.config import settings
from app.core.enums import AssetType, ProviderKind, ProviderType, SessionType
from app.core.models import FeedSpec, IngestedArticle, ProviderOutcome, SessionWindow
from app.services.news_service import NewsService


@pytest.fixture
def sample_session_window():
    now = datetime(2026, 10, 19, 14, 30, tzinfo=timezone.utc)
    return SessionWindow(
        market_timezone="America/New_York",
        session_type=SessionType.REGULAR_HOURS,
        is_market_open=True,
        window_start_utc=now - datetime.resolution * 0,
        window_start_et="2026-10-19T09:30:00",
        window_end_utc=now,
        window_end_et="2026-10-19T10:30:00",
        window_duration_hours=1.0,
        run_timestamp_utc=now,
        run_timestamp_et="2026-10-19T10:30:00",
    )


def test_clean_html_helpers():
    """Verify HTML cleaning strips tags and unescapes entities."""
    raw = "<p>Apple announced <b>record</b> services revenue &amp; earnings.</p>"
    cleaned = NewsService._clean_html(raw)
    assert cleaned == "Apple announced record services revenue & earnings."
    assert NewsService._clean_html("") == ""
    assert NewsService._clean_html(None) == ""


def test_clean_entry_title_removes_publisher_suffix():
    """Verify title cleaning strips publisher suffixes."""
    title = "NVIDIA reaches record high valuation - Reuters"
    cleaned = NewsService._clean_entry_title(title, "Reuters")
    assert cleaned == "NVIDIA reaches record high valuation"


def test_clean_entry_summary_removes_duplicate_headline():
    """Verify summary cleaning strips leading duplicated title text."""
    title = "Microsoft Expands Azure Infrastructure"
    summary = "<p>Microsoft Expands Azure Infrastructure. The company plans new regions across Europe.</p>"
    cleaned = NewsService._clean_entry_summary(summary, title, "Bloomberg")
    assert "The company plans new regions across Europe" in cleaned


def test_create_article_id_deterministic():
    """Verify deterministic hash ID generation."""
    id1 = NewsService._create_article_id("https://example.com/art1", "Sample Headline")
    id2 = NewsService._create_article_id("https://example.com/art1", "Sample Headline")
    assert id1 == id2
    assert len(id1) == 16


def test_fetch_yfinance_news_sync():
    """Verify synchronous Yahoo news fetch wrapper."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.news = [
            {
                "content": {
                    "title": "Tesla Delivery Beat",
                    "summary": "Tesla delivered more vehicles than estimated.",
                    "pubDate": "2026-10-19T12:00:00Z",
                    "provider": {"displayName": "Reuters"},
                    "canonicalUrl": {"url": "https://example.com/tsla-deliveries"},
                }
            }
        ]
        mock_ticker.return_value = mock_instance

        articles = NewsService._fetch_yfinance_news_sync("TSLA")
        assert len(articles) == 1
        assert articles[0].title == "Tesla Delivery Beat"
        assert articles[0].published_at_utc == datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)

        # When news is not a list
        mock_instance.news = None
        empty_articles = NewsService._fetch_yfinance_news_sync("TSLA")
        assert empty_articles == []


def test_fetch_feed_httpx_sync_success_and_failures():
    """Verify httpx feed fetching handles 200 OK, HTTP errors, and timeouts."""
    xml_sample = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title>Fed leaves benchmark rate unchanged</title>
          <link>https://example.com/fed-decision</link>
          <description>Rates hold steady.</description>
          <source url="https://reuters.com">Reuters</source>
        </item>
      </channel>
    </rss>"""

    # 1. Success 200 OK
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = xml_sample.encode("utf-8")
        mock_get.return_value = mock_resp

        articles = NewsService._fetch_feed_httpx_sync(
            "https://news.google.com/rss/test", "Reuters", ProviderType.GOOGLE_RSS_AGGREGATOR
        )
        assert len(articles) == 1
        assert "Fed leaves benchmark rate" in articles[0].title

    # 2. HTTP error (e.g. 503) raises exception
    with patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable", request=MagicMock(), response=mock_resp
        )
        mock_get.return_value = mock_resp

        with pytest.raises(httpx.HTTPStatusError):
            NewsService._fetch_feed_httpx_sync(
                "https://news.google.com/rss/test", "Reuters", ProviderType.GOOGLE_RSS_AGGREGATOR
            )

    # 3. Timeout error raises TimeoutException
    with patch("httpx.Client.get") as mock_get:
        mock_get.side_effect = httpx.ReadTimeout("Read timed out")

        with pytest.raises(httpx.ReadTimeout):
            NewsService._fetch_feed_httpx_sync(
                "https://news.google.com/rss/test", "Reuters", ProviderType.GOOGLE_RSS_AGGREGATOR
            )


@pytest.mark.asyncio
async def test_fetch_news_for_session_equity_parallel_sweep(sample_session_window):
    """Verify parallel ingestion sweep for equities across Yahoo and Google RSS sweeps."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    yf_article = IngestedArticle(
        article_id="yf_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/nvda-earnings",
        title="NVIDIA beats Q3 projections",
        summary="Data center demand drove record quarter.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    rss_article = IngestedArticle(
        article_id="rss_1",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Bloomberg",
        canonical_url="https://example.com/nvda-blackwell",
        title="NVIDIA accelerates Blackwell server production",
        summary="Enterprise customers scale infrastructure.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    with patch.object(NewsService, "_fetch_yfinance_news_sync", return_value=[yf_article]), \
         patch.object(NewsService, "_fetch_feed_httpx_sync", return_value=[rss_article]):

        articles, outcomes = await NewsService.fetch_news_for_session(
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            asset_type=AssetType.EQUITY,
            session=sample_session_window,
        )

        assert len(articles) >= 2
        assert outcomes["yfinance"]["status"] == "SUCCESS"
        assert outcomes["google_news_rss_total"]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_fetch_news_for_session_forex_sweep(sample_session_window):
    """Verify Forex feeds sweep activates specialized forex sources."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    fx_article = IngestedArticle(
        article_id="fx_1",
        provider=ProviderType.FXSTREET_RSS,
        source_name="FXStreet",
        canonical_url="https://example.com/eurusd-rally",
        title="EUR/USD rebounds toward 1.10 following ECB commentary",
        summary="European currency strengthens.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    with patch.object(NewsService, "_fetch_yfinance_news_sync", return_value=[]), \
         patch.object(NewsService, "_fetch_feed_httpx_sync", return_value=[fx_article]):

        articles, outcomes = await NewsService.fetch_news_for_session(
            ticker="EUR/USD",
            company_name="Euro / US Dollar",
            asset_type=AssetType.FOREX,
            session=sample_session_window,
        )

        assert len(articles) >= 1
        assert "forex_investing_com_forex" in outcomes
        assert "forex_fxstreet" in outcomes


@pytest.mark.asyncio
async def test_fetch_news_partial_provider_failure(sample_session_window):
    """Verify partial failure isolation: if Yahoo fails, Google RSS results are kept."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    rss_article = IngestedArticle(
        article_id="rss_only",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Wall Street Journal",
        canonical_url="https://example.com/wsj-aapl",
        title="Apple services revenue surges",
        summary="App Store and iCloud revenue drove growth.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    # Yahoo throws exception, RSS succeeds
    with patch.object(NewsService, "_fetch_yfinance_news_sync", side_effect=Exception("Yahoo connection refused")), \
         patch.object(NewsService, "_fetch_feed_httpx_sync", return_value=[rss_article]):

        articles, outcomes = await NewsService.fetch_news_for_session(
            ticker="AAPL",
            company_name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            session=sample_session_window,
        )

        assert len(articles) >= 1
        assert outcomes["yfinance"]["status"] == "FAILED"
        assert outcomes["google_news_rss_total"]["status"] == "SUCCESS"


@pytest.mark.asyncio
async def test_all_fetchers_start_before_any_finishes(sample_session_window):
    """Verify all fetchers start concurrently before any completes."""
    started_fetchers = set()
    first_finish_time = None

    async def fake_fetch(client, spec):
        nonlocal first_finish_time
        started_fetchers.add(spec.key)
        await asyncio.sleep(0.05)
        if first_finish_time is None:
            first_finish_time = time.time()
        return []

    with patch.object(NewsService, "_fetch_yfinance_news_sync", return_value=[]), \
         patch.object(NewsService, "_fetch_feed_httpx_async", side_effect=fake_fetch):
        _, outcomes = await NewsService.fetch_news_for_session(
            ticker="AAPL",
            company_name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            session=sample_session_window,
        )
        assert len(started_fetchers) > 0
        assert len(started_fetchers) == len(outcomes) - 1  # Excluding yfinance


@pytest.mark.asyncio
async def test_global_timeout_keeps_partial_results(sample_session_window):
    """Verify timeout cancels stragglers, marks TIMEOUT, but keeps partial successes."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    fast_article = IngestedArticle(
        article_id="fast_1",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Reuters",
        canonical_url="https://reuters.com/fast",
        title="Apple fast headline",
        summary="Summary",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    async def fake_fetch(client, spec):
        if "reuters" in spec.key:
            return [fast_article]
        # Straggler sleeps longer than timeout
        await asyncio.sleep(1.0)
        return []

    with patch.object(settings, "INGESTION_TIMEOUT_SECONDS", 0.1), \
         patch.object(NewsService, "_fetch_yfinance_news_sync", return_value=[]), \
         patch.object(NewsService, "_fetch_feed_httpx_async", side_effect=fake_fetch):
        articles, outcomes = await NewsService.fetch_news_for_session(
            ticker="AAPL",
            company_name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            session=sample_session_window,
        )
        assert len(articles) == 1
        assert articles[0].article_id == "fast_1"
        statuses = [po.status for po in outcomes]
        assert "SUCCESS" in statuses
        assert "TIMEOUT" in statuses


@pytest.mark.asyncio
async def test_html_200_fails_with_not_a_feed(sample_session_window):
    """Verify HTML 200 response (consent page) is rejected as NOT_A_FEED without retries."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.content = b"<!DOCTYPE html><html><body>Consent page</body></html>"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    spec = FeedSpec(
        key="rss_test",
        kind=ProviderKind.RSS_GOOGLE,
        url="https://news.google.com/rss/test",
        publisher="Test Pub",
        provider_type=ProviderType.GOOGLE_RSS_AGGREGATOR,
    )

    with pytest.raises(ValueError, match="NOT_A_FEED"):
        await NewsService._fetch_feed_httpx_async(mock_client, spec)

    # In fetch_news_for_session, error_code should be NOT_A_FEED
    with patch.object(NewsService, "_fetch_yfinance_news_sync", return_value=[]), \
         patch.object(mock_client, "get", return_value=mock_resp):
        _, outcomes = await NewsService.fetch_news_for_session(
            ticker="AAPL",
            company_name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            session=sample_session_window,
            http_client=mock_client,
        )
        feed_outcomes = [po for po in outcomes if po.kind == ProviderKind.RSS_GOOGLE]
        assert all(po.status == "FAILED" and po.error_code == "NOT_A_FEED" for po in feed_outcomes)


@pytest.mark.asyncio
async def test_503_then_200_retry_succeeds():
    """Verify tenacity retries on 503 and returns success when second attempt gives 200."""
    xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title>Apple announces new product</title>
          <link>https://example.com/aapl</link>
          <description>New hardware unveiled.</description>
          <source url="https://reuters.com">Reuters</source>
        </item>
      </channel>
    </rss>"""

    resp_503 = MagicMock()
    resp_503.status_code = 503
    resp_503.raise_for_status.side_effect = httpx.HTTPStatusError("503", request=MagicMock(), response=resp_503)

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.headers = {"content-type": "application/rss+xml"}
    resp_200.content = xml_content

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=[resp_503, resp_200])

    spec = FeedSpec(
        key="rss_test",
        kind=ProviderKind.RSS_GOOGLE,
        url="https://news.google.com/rss/test",
        publisher="Test Pub",
        provider_type=ProviderType.GOOGLE_RSS_AGGREGATOR,
    )

    articles = await NewsService._fetch_feed_httpx_async(mock_client, spec)
    assert len(articles) == 1
    assert "Apple announces new product" in articles[0].title
    assert mock_client.get.call_count == 2


def test_yahoo_news_count_passed():
    """Verify NewsService passes count=settings.YF_NEWS_COUNT to ticker.get_news()."""
    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.get_news.return_value = []
        mock_ticker.return_value = mock_instance

        NewsService._fetch_yfinance_news_sync("AAPL", count=75)
        mock_instance.get_news.assert_called_once_with(count=75)


@pytest.mark.asyncio
async def test_provider_outcome_kinds_drive_outage_detection():
    """Verify that orchestrator outage logic correctly relies on outcome.kind."""
    from app.core.models import Asset
    from app.services.orchestrator import AnalysisOrchestrator

    asset = Asset(ticker="AAPL", company_name="Apple Inc.", exchange="")

    # All providers fail -> DEGRADED
    failed_outcomes = [
        ProviderOutcome(key="yfinance", kind=ProviderKind.YFINANCE, status="FAILED", count=0),
        ProviderOutcome(key="rss_custom_feed", kind=ProviderKind.RSS_GOOGLE, status="FAILED", count=0),
    ]

    with patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=([], failed_outcomes)), \
         patch("app.db.repository.SentimentRepository.save_analysis_run"), \
         patch("app.db.repository.SentimentRepository.get_cached_run", return_value=None):
        mock_db = MagicMock()
        result = await AnalysisOrchestrator.run_pipeline("AAPL", mock_db, resolved_asset=asset)
        assert result.data_status.value == "DEGRADED"
        assert len(result.provider_outcomes) == 2


@pytest.mark.asyncio
async def test_ingestion_drops_only_exact_duplicate_article_id(sample_session_window):
    """Verify ingestion deduplication only drops identical article_id, keeping similar titles."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    art1 = IngestedArticle(
        article_id="exact_id_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/aapl-1",
        title="Apple Beats Q4 Estimates",
        summary="Summary 1",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    art1_dup = IngestedArticle(
        article_id="exact_id_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/aapl-1",
        title="Apple Beats Q4 Estimates",
        summary="Summary 1",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    art2_diff = IngestedArticle(
        article_id="diff_id_2",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Bloomberg",
        canonical_url="https://bloomberg.com/aapl-1",
        title="Apple Beats Q4 Estimates",
        summary="Summary 2",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    with patch.object(NewsService, "_fetch_yfinance_news_sync", return_value=[art1, art1_dup]), \
         patch.object(NewsService, "_fetch_feed_httpx_async", return_value=[art2_diff]):
        articles, outcomes = await NewsService.fetch_news_for_session(
            ticker="AAPL",
            company_name="Apple Inc.",
            asset_type=AssetType.EQUITY,
            session=sample_session_window,
        )
        article_ids = [a.article_id for a in articles]
        assert article_ids.count("exact_id_1") == 1
        assert "diff_id_2" in article_ids
        assert len(articles) == 2

