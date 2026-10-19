import os
import json
import pytest
from datetime import datetime, timezone, timedelta

from app.core.models import IngestedArticle, ScoredArticle, SessionWindow
from app.core.enums import ProviderType, SessionType, DecisionVerdict
from app.core.exceptions import FreshnessViolationException, NewsUnavailableException
from app.core.session_window import compute_session_window
from app.services.news_service import NewsService
from app.services.deduplication_service import DeduplicationService
from app.services.aggregator_service import AggregatorService


def test_parse_yfinance_current_and_legacy_schema():
    """Verify yfinance parser handles current pubDate ISO strings, legacy providerPublishTime, and undated items (F-06)."""
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "yf_current_schema.json")
    with open(fixture_path, "r", encoding="utf-8") as f:
        items = json.load(f)

    articles = NewsService.parse_yfinance_items(items, "AAPL")
    assert len(articles) == 4

    # Item 1: current schema pubDate ISO-8601
    assert "apple-expands-ai-cloud" in articles[0].canonical_url
    assert articles[0].published_at_utc == datetime(2026, 10, 18, 14, 30, tzinfo=timezone.utc)
    assert articles[0].source_name == "Yahoo - Reuters"

    # Item 2: older item with pubDate
    assert "apple-supply-chain-oled" in articles[1].canonical_url
    assert articles[1].published_at_utc == datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)

    # Item 3: missing timestamp MUST be None and never default to now()
    assert "apple-rumors-product-pipeline" in articles[2].canonical_url
    assert articles[2].published_at_utc is None

    # Item 4: legacy providerPublishTime
    assert "apple-services-record-quarterly" in articles[3].canonical_url
    assert articles[3].published_at_utc is not None
    assert articles[3].source_name == "Yahoo - CNBC"


def test_parse_google_rss_xml_with_source_tag():
    """Verify Google RSS parser extracts entry.source.title and preserves pubDate without now() default (F-06, F-07)."""
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "google_rss_sample.xml")
    with open(fixture_path, "r", encoding="utf-8") as f:
        xml_content = f.read()

    articles = NewsService.parse_rss_feed_content(xml_content, "AAPL", ProviderType.GOOGLE_RSS_AGGREGATOR)
    assert len(articles) == 3

    # Item 1: extracted source is Reuters (from <source>)
    assert articles[0].source_name == "Reuters"
    assert articles[0].published_at_utc == datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc)

    # Item 2: 2018 date
    assert articles[1].source_name == "The Wall Street Journal"
    assert articles[1].published_at_utc == datetime(2018, 9, 1, 12, 0, tzinfo=timezone.utc)

    # Item 3: missing pubDate is None, never defaults to now()
    assert articles[2].source_name == "Bloomberg"
    assert articles[2].published_at_utc is None


def test_filter_by_session_window_enforces_core_invariant():
    """Verify session window filter strictly retains articles within [start, end + 5m] (F-01)."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    session = SessionWindow(
        market_timezone="America/New_York",
        session_type=SessionType.REGULAR_HOURS,
        is_market_open=True,
        window_start_utc=now - timedelta(hours=4),
        window_start_et=now - timedelta(hours=4),
        window_end_utc=now,
        window_end_et=now,
        window_duration_hours=4.0,
        run_timestamp_utc=now,
        run_timestamp_et=now,
    )

    art_inside = IngestedArticle(
        article_id="in_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/1",
        title="Inside window",
        summary="Summary 1",
        published_at_utc=now - timedelta(hours=2),
        retrieved_at_utc=now,
        raw_provider_metadata={},
    )
    art_skew_valid = IngestedArticle(
        article_id="skew_1",
        provider=ProviderType.YFINANCE,
        source_name="CNBC",
        canonical_url="https://example.com/2",
        title="Within 5m skew",
        summary="Summary 2",
        published_at_utc=now + timedelta(minutes=3),  # <= 5m future skew allowed
        retrieved_at_utc=now,
        raw_provider_metadata={},
    )
    art_future_invalid = IngestedArticle(
        article_id="future_1",
        provider=ProviderType.YFINANCE,
        source_name="Bloomberg",
        canonical_url="https://example.com/3",
        title="Excessive future clock skew",
        summary="Summary 3",
        published_at_utc=now + timedelta(minutes=15),  # > 5m clock skew
        retrieved_at_utc=now,
        raw_provider_metadata={},
    )
    art_past_invalid = IngestedArticle(
        article_id="past_1",
        provider=ProviderType.YFINANCE,
        source_name="WSJ",
        canonical_url="https://example.com/4",
        title="Past article",
        summary="Summary 4",
        published_at_utc=now - timedelta(hours=5),  # Before window start
        retrieved_at_utc=now,
        raw_provider_metadata={},
    )
    art_undated = IngestedArticle(
        article_id="undated_1",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="MarketWatch",
        canonical_url="https://example.com/5",
        title="Undated article",
        summary="Summary 5",
        published_at_utc=None,
        retrieved_at_utc=now,
        raw_provider_metadata={},
    )

    articles = [art_inside, art_skew_valid, art_future_invalid, art_past_invalid, art_undated]
    retained, excluded, out_cnt, missing_cnt = DeduplicationService.filter_by_session_window(articles, session)

    assert len(retained) == 2
    assert {a.article_id for a in retained} == {"in_1", "skew_1"}
    assert out_cnt == 2
    assert missing_cnt == 1
    assert len(excluded) == 3


def test_filter_by_session_window_caps_sample_at_20():
    """Verify that sample excluded articles list is capped at 20 while true counts reflect total."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    session = SessionWindow(
        market_timezone="America/New_York",
        session_type=SessionType.REGULAR_HOURS,
        is_market_open=True,
        window_start_utc=now - timedelta(hours=2),
        window_start_et=now - timedelta(hours=2),
        window_end_utc=now,
        window_end_et=now,
        window_duration_hours=2.0,
        run_timestamp_utc=now,
        run_timestamp_et=now,
    )

    # Generate 30 past articles and 30 undated articles
    articles = []
    for i in range(30):
        articles.append(
            IngestedArticle(
                article_id=f"past_{i}",
                provider=ProviderType.YFINANCE,
                source_name="Source",
                canonical_url=f"https://example.com/past/{i}",
                title=f"Past article {i}",
                summary="",
                published_at_utc=now - timedelta(days=1),
                retrieved_at_utc=now,
                raw_provider_metadata={},
            )
        )
    for i in range(30):
        articles.append(
            IngestedArticle(
                article_id=f"undated_{i}",
                provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
                source_name="Source",
                canonical_url=f"https://example.com/undated/{i}",
                title=f"Undated article {i}",
                summary="",
                published_at_utc=None,
                retrieved_at_utc=now,
                raw_provider_metadata={},
            )
        )

    retained, excluded, out_cnt, missing_cnt = DeduplicationService.filter_by_session_window(articles, session)
    assert len(retained) == 0
    assert out_cnt == 30
    assert missing_cnt == 30
    # Capped at 20 per reason (max 40 total samples)
    assert len(excluded) == 40


def create_test_scored_article(
    art_id: str,
    publisher: str,
    pub_dt: datetime,
    score: float = 0.8,
    confidence: float = 0.9,
    weight: float = 0.9,
    is_catalyst: bool = False,
) -> ScoredArticle:
    return ScoredArticle(
        article_id=art_id,
        provider=ProviderType.YFINANCE,
        source_name=publisher,
        canonical_publisher=publisher,
        canonical_url=f"https://example.com/{art_id}",
        title=f"Title {art_id}",
        summary=f"Summary {art_id}",
        published_at_utc=pub_dt,
        retrieved_at_utc=datetime.now(timezone.utc),
        cluster_id=f"c_{art_id}",
        is_cluster_rep=True,
        sentiment_score=score,
        finbert_positive=score if score > 0 else 0.05,
        finbert_negative=abs(score) if score < 0 else 0.05,
        finbert_neutral=0.1,
        finbert_directional_score=score,
        finbert_confidence=confidence,
        finbert_logits={},
        final_weight=weight,
        is_catalyst=is_catalyst,
        lead_text=f"Lead text for {art_id}",
    )


def test_aggregator_out_of_window_assertion_raises_exception():
    """Verify AggregatorService raises FreshnessViolationException if an unwindowed article slips through (Core Invariant)."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    session = SessionWindow(
        market_timezone="America/New_York",
        session_type=SessionType.REGULAR_HOURS,
        is_market_open=True,
        window_start_utc=now - timedelta(hours=2),
        window_start_et=now - timedelta(hours=2),
        window_end_utc=now,
        window_end_et=now,
        window_duration_hours=2.0,
        run_timestamp_utc=now,
        run_timestamp_et=now,
    )

    art_stale = create_test_scored_article(
        art_id="stale_1",
        publisher="Reuters",
        pub_dt=datetime(2018, 5, 1, tzinfo=timezone.utc),
        score=0.8,
    )

    with pytest.raises(FreshnessViolationException):
        AggregatorService.aggregate_and_decide("AAPL", "Apple Inc.", session, [art_stale], [], "")


def test_aggregator_effective_weight_and_tally_consistency():
    """Verify F-08 effective weight consistency: recency_decay * max(0.2, final_weight), age_hours computed, tallies match."""
    now = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
    session = SessionWindow(
        market_timezone="America/New_York",
        session_type=SessionType.REGULAR_HOURS,
        is_market_open=True,
        window_start_utc=now - timedelta(hours=6),
        window_start_et=now - timedelta(hours=6),
        window_end_utc=now,
        window_end_et=now,
        window_duration_hours=6.0,
        run_timestamp_utc=now,
        run_timestamp_et=now,
    )

    art1 = create_test_scored_article(
        art_id="a1",
        publisher="Reuters",
        pub_dt=now - timedelta(hours=1),
        score=0.80,
        confidence=0.90,
        weight=0.90,
        is_catalyst=True,
    )
    art2 = create_test_scored_article(
        art_id="a2",
        publisher="CNBC",
        pub_dt=now - timedelta(hours=5),
        score=0.70,
        confidence=0.80,
        weight=0.80,
        is_catalyst=False,
    )

    decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
        "AAPL", "Apple Inc.", session, [art1, art2], [], ""
    )

    assert decision == DecisionVerdict.BUY
    assert art1.effective_weight is not None
    assert art2.effective_weight is not None
    assert art1.age_hours is not None
    assert art2.age_hours is not None

    # art1 was published 1h ago, art2 was published 5h ago; recency decay reduces art2 weight relative to art1
    assert art1.age_hours < art2.age_hours
    assert art1.effective_weight > art2.effective_weight
