from datetime import datetime, timezone
from app.services.deduplication_service import DeduplicationService
from app.core.models import IngestedArticle
from app.core.enums import ProviderType, ExclusionReason


def test_canonicalize_url():
    raw_url = "https://www.reuters.com/business/tech/apple-results/?utm_source=twitter&utm_medium=social&fbclid=12345#comments"
    expected = "https://www.reuters.com/business/tech/apple-results"
    assert DeduplicationService.canonicalize_url(raw_url) == expected


def test_normalize_publisher():
    assert DeduplicationService.normalize_publisher("Yahoo - Reuters") == "Reuters"
    assert DeduplicationService.normalize_publisher("CNBC.com") == "CNBC"
    assert DeduplicationService.normalize_publisher("The Wall Street Journal") == "Wall Street Journal"
    assert DeduplicationService.normalize_publisher("PR Newswire via Yahoo") == "PR Newswire"
    assert DeduplicationService.normalize_publisher("Google News RSS") == "Unknown Aggregator"


def test_jaccard_similarity():
    h1 = "Apple reports strong Q4 revenue beat driven by cloud services"
    h2 = "Apple reports strong Q4 revenue beat driven by cloud services growth"
    sim = DeduplicationService.jaccard_similarity(h1, h2)
    assert sim >= 0.80

    h3 = "Federal Reserve signals potential rate pause in upcoming meeting"
    sim_diff = DeduplicationService.jaccard_similarity(h1, h3)
    assert sim_diff < 0.10


def test_entity_relevance_filter():
    now = datetime.now(timezone.utc)
    rel_art = IngestedArticle(
        article_id="1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/1",
        title="Apple unveils new iPad mini with A17 Pro chip",
        summary="Apple Inc announced the latest iPad model.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(rel_art, "AAPL", "Apple Inc.") is True

    irrel_art = IngestedArticle(
        article_id="2",
        provider=ProviderType.YFINANCE,
        source_name="MarketWatch",
        canonical_url="https://marketwatch.com/2",
        title="10 tech stocks to watch as Treasury yields decline",
        summary="General market discussion on bond yields affecting tech valuations broadly.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(irrel_art, "AAPL", "Apple Inc.") is False


def test_multi_asset_entity_relevance_filter():
    now = datetime.now(timezone.utc)
    fx_art = IngestedArticle(
        article_id="fx1",
        provider=ProviderType.INVESTING_FOREX_RSS,
        source_name="Investing.com Forex",
        canonical_url="https://investing.com/fx1",
        title="EUR/USD rises towards 1.09 as ECB holds interest rates steady",
        summary="The Euro strengthened against the US Dollar following the policy meeting.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(fx_art, "EUR/USD", "Euro / US Dollar") is True
    assert DeduplicationService.is_materially_relevant(fx_art, "GC=F", "Gold Futures") is False

    gold_art = IngestedArticle(
        article_id="gold1",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Reuters",
        canonical_url="https://reuters.com/gold1",
        title="Gold prices scale fresh record highs as bullion demand surges",
        summary="Gold prices hit another milestone today.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(gold_art, "GC=F", "Gold Futures") is True
    assert DeduplicationService.is_materially_relevant(gold_art, "BTC-USD", "Bitcoin USD") is False



def test_deduplication_pipeline():
    t0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 16, 12, 5, 0, tzinfo=timezone.utc)

    art1 = IngestedArticle(
        article_id="orig",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/article1?utm_source=rss",
        title="Apple Beats Q4 Earnings Expectations on Strong iPhone Sales",
        summary="Apple reported quarterly profit surpassing consensus.",
        published_at_utc=t0,
        retrieved_at_utc=t0,
    )
    # Syndicated reprint
    art2 = IngestedArticle(
        article_id="synd",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Yahoo Finance",
        canonical_url="https://finance.yahoo.com/reprint/article1",
        title="Apple Beats Q4 Earnings Expectations on Strong iPhone Sales",
        summary="Apple reported quarterly profit surpassing consensus.",
        published_at_utc=t1,
        retrieved_at_utc=t1,
    )
    # Irrelevant article
    art3 = IngestedArticle(
        article_id="irrel",
        provider=ProviderType.YFINANCE,
        source_name="CNBC",
        canonical_url="https://cnbc.com/oil-slips",
        title="Crude Oil Prices Drop Amid Global Demand Concerns",
        summary="Energy commodities drifted lower today.",
        published_at_utc=t0,
        retrieved_at_utc=t0,
    )

    retained, excluded, clusters = DeduplicationService.process_and_deduplicate(
        [art1, art2, art3], "AAPL", "Apple Inc."
    )

    assert len(retained) == 1
    assert retained[0].article_id == "orig"

    assert len(excluded) == 2
    reasons = {e[1] for e in excluded}
    assert ExclusionReason.DUPLICATE_SYNDICATION in reasons
    assert ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE in reasons
