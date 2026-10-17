import asyncio
import hashlib
import time
import urllib.parse
from datetime import datetime, timezone
import feedparser
import yfinance as yf
from app.core.models import IngestedArticle
from app.core.enums import ProviderType, AssetType
from app.core.session_window import SessionWindow
from app.utils.logging import logger

EQUITY_SOURCES = [
    "Reuters",
    "Bloomberg",
    "CNBC",
    "Wall Street Journal",
    "MarketWatch",
    "Seeking Alpha",
    "Motley Fool",
]

FOREX_COMMODITY_SOURCES = [
    "Reuters",
    "Bloomberg",
    "CNBC",
    "Wall Street Journal",
    "MarketWatch",
]


class NewsService:
    @staticmethod
    def _create_article_id(canonical_url: str, title: str) -> str:
        raw = f"{canonical_url.strip()}|{title.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @classmethod
    async def fetch_news_for_session(
        cls,
        ticker: str,
        company_name: str,
        session: SessionWindow,
        asset_type: AssetType = AssetType.EQUITY,
        yf_symbol: str = "",
    ) -> tuple[list[IngestedArticle], dict[str, dict]]:
        """
        Massive multi-source news ingestion (up to 300+ headlines across 8+ sources):
        1. Yahoo Finance (API + RSS)
        2. Forex/Commodity dedicated feeds (Investing.com Forex, FXStreet, Yahoo FX RSS)
        3. Google News RSS across top financial outlets (Reuters, Bloomberg, CNBC, WSJ, MarketWatch, etc.)
        """
        yf_ticker = yf_symbol or ticker
        provider_outcomes: dict[str, dict] = {}
        all_articles: list[IngestedArticle] = []
        seen_urls = set()
        seen_titles = set()

        def add_article(art: IngestedArticle):
            url_norm = art.canonical_url.split("?")[0].rstrip("/").lower()
            title_norm = art.title.strip().lower()
            if url_norm and url_norm in seen_urls:
                return
            if title_norm and title_norm in seen_titles:
                return
            seen_urls.add(url_norm)
            seen_titles.add(title_norm)
            all_articles.append(art)

        # 1. Fetch Yahoo Finance API News in worker thread
        t0 = time.time()
        try:
            yf_items = await asyncio.to_thread(cls._fetch_yfinance_news_sync, yf_ticker)
            for item in yf_items:
                add_article(item)
            provider_outcomes["yfinance"] = {
                "status": "SUCCESS",
                "count": len(yf_items),
                "latency_ms": round((time.time() - t0) * 1000, 1),
            }
        except Exception as e:
            logger.warning(f"Error fetching yfinance news for {yf_ticker}: {e}")
            provider_outcomes["yfinance"] = {
                "status": "FAILED",
                "error": str(e),
                "count": 0,
                "latency_ms": round((time.time() - t0) * 1000, 1),
            }

        # 2. If Forex, fetch dedicated Forex feeds
        if asset_type == AssetType.FOREX or "/" in ticker or "=X" in yf_ticker:
            t_fx = time.time()
            fx_tasks = [
                asyncio.to_thread(
                    cls._fetch_direct_rss_sync,
                    "Investing.com Forex",
                    "https://www.investing.com/rss/news_1.rss",
                    ProviderType.INVESTING_FOREX_RSS,
                ),
                asyncio.to_thread(
                    cls._fetch_direct_rss_sync,
                    "FXStreet",
                    "https://www.fxstreet.com/rss/news",
                    ProviderType.FXSTREET_RSS,
                ),
                asyncio.to_thread(
                    cls._fetch_direct_rss_sync,
                    "Yahoo Finance Forex RSS",
                    f"https://finance.yahoo.com/rss/headline?s={yf_ticker}",
                    ProviderType.YFINANCE,
                ),
            ]
            fx_results = await asyncio.gather(*fx_tasks, return_exceptions=True)
            fx_count = 0
            for res in fx_results:
                if isinstance(res, list):
                    for item in res:
                        add_article(item)
                        fx_count += 1
            provider_outcomes["forex_direct_feeds"] = {
                "status": "SUCCESS",
                "count": fx_count,
                "latency_ms": round((time.time() - t_fx) * 1000, 1),
            }

        # 3. Choose Google News publishers based on asset class
        if asset_type in (AssetType.FOREX, AssetType.COMMODITY):
            target_sources = FOREX_COMMODITY_SOURCES
        else:
            target_sources = EQUITY_SOURCES

        # 4. Fetch Google News RSS for each publisher in parallel
        t_rss = time.time()
        rss_tasks = []
        for src in target_sources:
            # Query string: use clean symbol (e.g. "EUR/USD" or "NVDA")
            query_str = ticker
            rss_tasks.append(
                asyncio.to_thread(cls._fetch_google_rss_source_sync, query_str, src)
            )

        rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)
        rss_count = 0
        for src_name, res in zip(target_sources, rss_results):
            if isinstance(res, list):
                for item in res:
                    add_article(item)
                    rss_count += 1
                provider_outcomes[f"rss_{src_name.lower().replace(' ', '_')}"] = {
                    "status": "SUCCESS",
                    "count": len(res),
                }
            else:
                provider_outcomes[f"rss_{src_name.lower().replace(' ', '_')}"] = {
                    "status": "FAILED",
                    "error": str(res),
                    "count": 0,
                }

        provider_outcomes["google_news_rss_total"] = {
            "status": "SUCCESS",
            "count": rss_count,
            "latency_ms": round((time.time() - t_rss) * 1000, 1),
        }

        logger.info(
            f"Ingestion sweep completed for {ticker} ({asset_type.value}): "
            f"{len(all_articles)} unique headlines ingested across {len(provider_outcomes)} feeds."
        )
        return all_articles, provider_outcomes

    @classmethod
    def _fetch_yfinance_news_sync(cls, yf_ticker: str) -> list[IngestedArticle]:
        """Fetches all available recent news articles from yfinance API."""
        ticker_obj = yf.Ticker(yf_ticker)
        news_items = getattr(ticker_obj, "news", [])
        if not isinstance(news_items, list):
            return []

        articles: list[IngestedArticle] = []
        now = datetime.now(timezone.utc)

        for item in news_items:
            if not isinstance(item, dict):
                continue

            # Title extraction
            if "content" in item and isinstance(item["content"], dict) and "title" in item["content"]:
                title = item["content"]["title"]
            else:
                title = item.get("title", "")

            title = title.strip()
            if not title:
                continue

            # Publisher
            publisher = ""
            if "provider" in item and isinstance(item["provider"], dict):
                publisher = item["provider"].get("displayName", "")
            if not publisher:
                publisher = item.get("publisher", "Yahoo Finance")

            # Link
            link = ""
            if "content" in item and isinstance(item["content"], dict):
                link = item["content"].get("clickThroughUrl", {}).get("url", "")
            if not link:
                link = item.get("link", f"https://finance.yahoo.com/quote/{yf_ticker}")

            # Summary
            summary = ""
            if "content" in item and isinstance(item["content"], dict):
                summary = item["content"].get("summary", "") or item["content"].get("description", "")
            if not summary:
                summary = item.get("summary", "")

            # Timestamp
            pub_time = now
            pub_ts = item.get("providerPublishTime")
            if pub_ts:
                try:
                    pub_time = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
                except Exception:
                    pass

            art_id = cls._create_article_id(link, title)
            articles.append(
                IngestedArticle(
                    article_id=art_id,
                    provider=ProviderType.YFINANCE,
                    source_name=f"Yahoo - {publisher}",
                    canonical_url=link,
                    title=title,
                    summary=summary[:1000] if summary else "",
                    published_at_utc=pub_time,
                    retrieved_at_utc=now,
                    raw_provider_metadata={"yf_publisher": publisher},
                )
            )

        return articles

    @classmethod
    def _fetch_google_rss_source_sync(cls, query_symbol: str, source_name: str) -> list[IngestedArticle]:
        """Queries Google News RSS for a specific financial publisher (up to 50 headlines)."""
        articles: list[IngestedArticle] = []
        now = datetime.now(timezone.utc)

        try:
            query = f"{query_symbol} {source_name}"
            encoded = urllib.parse.quote_plus(query)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

            feed = feedparser.parse(url)
            for entry in feed.entries[:50]:
                title = cls._clean_html(getattr(entry, "title", ""))
                link = getattr(entry, "link", "")
                summary = cls._clean_html(getattr(entry, "summary", ""))

                if not title:
                    continue

                # Parse publication time if present
                pub_time = now
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass

                art_id = cls._create_article_id(link, title)
                articles.append(
                    IngestedArticle(
                        article_id=art_id,
                        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
                        source_name=source_name,
                        canonical_url=link,
                        title=title,
                        summary=summary[:1000],
                        published_at_utc=pub_time,
                        retrieved_at_utc=now,
                        raw_provider_metadata={"rss_source": source_name},
                    )
                )
        except Exception as e:
            logger.warning(f"Error fetching Google RSS for {query_symbol} from {source_name}: {e}")

        return articles

    @classmethod
    def _fetch_direct_rss_sync(cls, feed_name: str, rss_url: str, provider: ProviderType) -> list[IngestedArticle]:
        """Fetches from a direct RSS endpoint (e.g. Investing.com Forex, FXStreet)."""
        articles: list[IngestedArticle] = []
        now = datetime.now(timezone.utc)

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:50]:
                title = cls._clean_html(getattr(entry, "title", ""))
                link = getattr(entry, "link", "")
                summary = cls._clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))

                if not title:
                    continue

                pub_time = now
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                    except Exception:
                        pass

                art_id = cls._create_article_id(link, title)
                articles.append(
                    IngestedArticle(
                        article_id=art_id,
                        provider=provider,
                        source_name=feed_name,
                        canonical_url=link,
                        title=title,
                        summary=summary[:1000],
                        published_at_utc=pub_time,
                        retrieved_at_utc=now,
                        raw_provider_metadata={"direct_feed": feed_name},
                    )
                )
        except Exception as e:
            logger.warning(f"Error fetching direct RSS {feed_name} ({rss_url}): {e}")

        return articles

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strips HTML tags, collapses whitespace, and unescapes HTML entities."""
        if not text:
            return ""
        import html
        import re
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()
