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


def test_normalize_publisher_whole_word_boundaries():
    """Verify F-11: Short publisher abbreviations like 'ap' do not match inside words like 'Snap' or 'Apple'."""
    # Matches genuine Associated Press
    assert DeduplicationService.normalize_publisher("Associated Press") == "Associated Press"
    assert DeduplicationService.normalize_publisher("AP News") == "Associated Press"

    # Must NOT match 'ap' inside Snap, Apple, or Japanese
    assert DeduplicationService.normalize_publisher("Snap Newsroom") == "Snap Newsroom"
    assert DeduplicationService.normalize_publisher("Apple PR") == "Apple PR"
    assert DeduplicationService.normalize_publisher("Japanese Tech Daily") == "Japanese Tech Daily"


def test_entity_relevance_short_ticker_protection():
    """Verify F-10: 1-2 char tickers (e.g. 'A', 'AI') require cash-tag or company name, avoiding common word matches."""
    now = datetime.now(timezone.utc)

    # False positive text containing bare 'a'
    art_bare_a = IngestedArticle(
        article_id="bare_a",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/a",
        title="A major new corporate report details broad economic indicators",
        summary="Analysts reviewed standard GDP data yesterday afternoon.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    # Ticker 'A' without cash tag or company name MUST NOT match
    assert DeduplicationService.is_materially_relevant(art_bare_a, "A", "Agilent Technologies Inc.") is False

    # Genuine cash tag mention $A MUST match
    art_cash_a = IngestedArticle(
        article_id="cash_a",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/cash_a",
        title="Investors buy shares of $A following quarterly profit beat",
        summary="Positive momentum observed in today's trading session.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_cash_a, "A", "Agilent Technologies Inc.") is True

    # Genuine company name mention (stripped of 'Inc.') MUST match
    art_comp_a = IngestedArticle(
        article_id="comp_a",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/comp_a",
        title="Agilent announces breakthrough diagnostic equipment",
        summary="New laboratory products launch globally.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_comp_a, "A", "Agilent Technologies Inc.") is True

    # Substring 'ai' inside 'said' or 'daily' MUST NOT match ticker 'AI'
    art_substring_ai = IngestedArticle(
        article_id="sub_ai",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/sub_ai",
        title="Executives said daily retail store traffic improved",
        summary="Retail performance was steady.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_substring_ai, "AI", "C3.ai, Inc.") is False


def test_process_and_deduplicate_sorts_newest_first_before_truncation():
    """Verify F-05: When truncation occurs at max_articles, newest articles are retained."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    # 3 relevant articles with distinct timestamps
    art_oldest = IngestedArticle(
        article_id="oldest",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/old",
        title="Apple launches product update",
        summary="Apple Inc product details.",
        published_at_utc=now - timedelta(hours=3),
        retrieved_at_utc=now,
    )
    art_middle = IngestedArticle(
        article_id="middle",
        provider=ProviderType.YFINANCE,
        source_name="CNBC",
        canonical_url="https://example.com/mid",
        title="Apple reports services acceleration",
        summary="Apple Inc services growth.",
        published_at_utc=now - timedelta(hours=2),
        retrieved_at_utc=now,
    )
    art_newest = IngestedArticle(
        article_id="newest",
        provider=ProviderType.YFINANCE,
        source_name="Bloomberg",
        canonical_url="https://example.com/new",
        title="Apple expands enterprise cloud data centers",
        summary="Apple Inc cloud expansion.",
        published_at_utc=now - timedelta(hours=1),
        retrieved_at_utc=now,
    )

    # Pass in unsorted order and truncate to max_articles=2
    retained, excluded, clusters = DeduplicationService.process_and_deduplicate(
        [art_oldest, art_newest, art_middle], "AAPL", "Apple Inc.", max_articles=2
    )

    assert len(retained) == 2
    # The retained articles must be the two newest: 'newest' and 'middle'
    retained_ids = {a.article_id for a in retained}
    assert "newest" in retained_ids
    assert "middle" in retained_ids
    assert "oldest" not in retained_ids


def test_normalize_publisher_yahoo_x():
    """Verify normalize_publisher handles 'Yahoo - X' by returning normalized X, not 'Yahoo Finance'."""
    assert DeduplicationService.normalize_publisher("Yahoo - Reuters") == "Reuters"
    assert DeduplicationService.normalize_publisher("Yahoo - Bloomberg") == "Bloomberg"
    assert DeduplicationService.normalize_publisher("Yahoo - CNBC") == "CNBC"
    assert DeduplicationService.normalize_publisher("Yahoo - Benzinga") == "Benzinga"
    assert DeduplicationService.normalize_publisher("Yahoo Finance - TipRanks") == "TipRanks"
    assert DeduplicationService.normalize_publisher("Yahoo - Wall Street Journal") == "Wall Street Journal"
    assert DeduplicationService.normalize_publisher("Yahoo - WSJ") == "Wall Street Journal"


def test_relevance_distinctive_tokens_and_raw_att():
    """
    Verify relevance matching:
    - Stop matching on any single company-name token
    - Require full name, or first distinctive token (excluding generic tokens)
    - Match AT&T on its raw form
    - Regression tests: GM vs 'General Electric', TGT vs 'target', AMD vs 'Advanced manufacturing', T vs 'AT&T raises dividend'
    """
    now = datetime.now(timezone.utc)

    # 1. GM vs "General Electric" (False)
    art_ge = IngestedArticle(
        article_id="ge_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/ge1",
        title="General Electric completes corporate separation plan",
        summary="GE announces aerospace and energy industrial division updates.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_ge, "GM", "General Motors Company") is False

    # 2. TGT vs "target" (False)
    art_tgt = IngestedArticle(
        article_id="tgt_1",
        provider=ProviderType.YFINANCE,
        source_name="Bloomberg",
        canonical_url="https://bloomberg.com/tgt1",
        title="Federal Reserve says inflation target remains 2 percent",
        summary="Policymakers reiterated their commitment to hitting the macroeconomic target.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_tgt, "TGT", "Target Corporation") is False

    # 3. AMD vs "Advanced manufacturing" (False)
    art_amd = IngestedArticle(
        article_id="amd_1",
        provider=ProviderType.YFINANCE,
        source_name="CNBC",
        canonical_url="https://cnbc.com/amd1",
        title="Advanced manufacturing investments rise across US industrial corridor",
        summary="Factories adopt modern automated assembly line tools.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_amd, "AMD", "Advanced Micro Devices, Inc.") is False

    # 4. T vs "AT&T raises dividend" (True)
    art_att = IngestedArticle(
        article_id="att_1",
        provider=ProviderType.YFINANCE,
        source_name="Wall Street Journal",
        canonical_url="https://wsj.com/att1",
        title="AT&T raises dividend following strong fiber broadband subscribers growth",
        summary="Telecommunications giant AT&T posts solid quarterly cash flow.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    assert DeduplicationService.is_materially_relevant(art_att, "T", "AT&T Inc.") is True


def test_env_example_matches_config_defaults():
    """Verify .env.example defaults match config.py settings exactly."""
    import os
    from app.config import settings

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env.example")
    assert os.path.exists(env_path)

    env_vars = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    assert int(env_vars["MAX_RETAINED_ARTICLES"]) == settings.MAX_RETAINED_ARTICLES == 350
    assert int(env_vars["MAX_LLM_CANDIDATES"]) == settings.MAX_LLM_CANDIDATES == 100
    assert int(env_vars["MAX_EXCERPT_TOKENS"]) == settings.MAX_EXCERPT_TOKENS == 150
    assert int(env_vars["MAX_PROMPT_TOKENS"]) == settings.MAX_PROMPT_TOKENS == 8000
    assert int(env_vars["MAX_COMPLETION_TOKENS"]) == settings.MAX_COMPLETION_TOKENS == 1000
    assert float(env_vars["MAX_COST_PER_RUN_USD"]) == settings.MAX_COST_PER_RUN_USD == 0.05
    assert env_vars["LLM_MODEL_ID"] == settings.LLM_MODEL_ID == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert env_vars["FINBERT_MODEL_NAME"] == settings.FINBERT_MODEL_NAME == "ProsusAI/finbert"
    assert env_vars["LLM_FALLBACK_MODEL_ID"] == settings.LLM_FALLBACK_MODEL_ID == ""
