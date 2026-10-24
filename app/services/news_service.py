import asyncio
import hashlib
import html
import math
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import feedparser
import httpx
import tenacity
import yfinance as yf

from app.config import settings
from app.core.models import IngestedArticle, FeedSpec, ProviderOutcome
from app.core.enums import ProviderType, ProviderKind, AssetType
from app.core.session_window import SessionWindow
from app.core.asset_registry import build_google_query_subject
from app.utils.logging import logger


def _as_dict(value: Any) -> dict:
    """Safely return value as a dictionary if it is one, else an empty dictionary."""
    return value if isinstance(value, dict) else {}


EQUITY_PUBLISHER_DOMAINS = {
    "Reuters": "reuters.com",
    "Bloomberg": "bloomberg.com",
    "CNBC": "cnbc.com",
    "Wall Street Journal": "wsj.com",
    "MarketWatch": "marketwatch.com",
    "Seeking Alpha": "seekingalpha.com",
    "Motley Fool": "fool.com",
}

FOREX_COMMODITY_PUBLISHER_DOMAINS = {
    "Reuters": "reuters.com",
    "Bloomberg": "bloomberg.com",
    "CNBC": "cnbc.com",
    "Wall Street Journal": "wsj.com",
    "MarketWatch": "marketwatch.com",
}

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "syndication", "ocid", "guccounter", "ncid"
}


class ProviderOutcomeList(list):
    """List of ProviderOutcome instances with backward-compatible dict-like lookup."""

    def __getitem__(self, key):
        if isinstance(key, str):
            if key == "google_news_rss_total":
                rss_items = [
                    item for item in self
                    if getattr(item, "kind", None) in (ProviderKind.RSS_GOOGLE, ProviderKind.RSS_DIRECT)
                ]
                any_success = any(item.status == "SUCCESS" for item in rss_items)
                total_count = sum(item.count for item in rss_items if item.status == "SUCCESS")
                return ProviderOutcome(
                    key="google_news_rss_total",
                    kind=ProviderKind.RSS_GOOGLE,
                    status="SUCCESS" if any_success else "FAILED",
                    count=total_count,
                    latency_ms=0.0,
                )
            for item in self:
                if getattr(item, "key", None) == key:
                    return item
            raise KeyError(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, str):
            if key in self:
                return self[key]
            return default
        return default

    def __contains__(self, key):
        if isinstance(key, str):
            if key == "google_news_rss_total":
                return any(
                    getattr(item, "kind", None) in (ProviderKind.RSS_GOOGLE, ProviderKind.RSS_DIRECT)
                    for item in self
                )
            return any(getattr(item, "key", None) == key for item in self)
        return super().__contains__(key)


class NewsService:
    @staticmethod
    def canonicalize_url(raw_url: str) -> str:
        """Strips query tracking parameters, anchors, and trailing slashes. Non-http(s) URLs become empty."""
        if not raw_url:
            return ""
        parsed = urllib.parse.urlparse(raw_url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return ""
        query_pairs = urllib.parse.parse_qsl(parsed.query)
        cleaned_query = [
            (k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS
        ]
        new_query = urllib.parse.urlencode(cleaned_query)
        path = parsed.path.rstrip("/")
        return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", new_query, ""))

    @staticmethod
    def _create_article_id(canonical_url: str, title: str) -> str:
        raw = f"{canonical_url.strip()}|{title.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _clean_html(text: str) -> str:
        """Strips HTML tags, collapses whitespace, and unescapes HTML entities."""
        if not text:
            return ""
        cleaned = re.sub(r"<[^>]+>", " ", text)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @classmethod
    def _clean_entry_title(cls, raw_title: str, publisher: str) -> str:
        """Clean HTML and strip trailing ' - <Publisher>' when matching source."""
        title = cls._clean_html(raw_title)
        if publisher:
            pattern = rf"\s*-\s*{re.escape(publisher.strip())}\s*$"
            title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()
        return title

    @classmethod
    def _clean_entry_summary(cls, raw_summary: str, cleaned_title: str, publisher: str) -> str:
        """
        Drop summary when, after HTML stripping, case, and whitespace normalisation,
        it equals the title or the title plus publisher.
        Also strip leading duplicated title text if present.
        """
        summary = cls._clean_html(raw_summary)
        norm_sum = re.sub(r"\s+", " ", summary).strip().lower()
        norm_title = re.sub(r"\s+", " ", cleaned_title).strip().lower()
        norm_title_pub = re.sub(r"\s+", " ", f"{cleaned_title} {publisher}").strip().lower()

        if norm_sum in (norm_title, norm_title_pub) or not norm_sum:
            return ""

        # Strip leading duplicate title if present
        if cleaned_title and summary.lower().startswith(cleaned_title.lower()):
            stripped_leading = summary[len(cleaned_title):].lstrip(" .:-–—")
            if stripped_leading:
                summary = stripped_leading

        return summary[:1000]

    @classmethod
    def parse_yfinance_items(cls, news_items: list[dict], yf_ticker: str) -> list[IngestedArticle]:
        """
        Parses raw yfinance news items supporting both the current schema:
        {"id": ..., "content": {"title", "summary", "pubDate" (ISO-8601, Z), "provider": {"displayName"}, ...}}
        and legacy keys (providerPublishTime, top-level title, publisher, link).
        Never defaults timestamps to now().
        """
        articles: list[IngestedArticle] = []
        now = datetime.now(timezone.utc)

        for item in news_items:
            if not isinstance(item, dict):
                continue

            content = _as_dict(item.get("content"))

            # Title
            title = content.get("title") or item.get("title", "")
            title = cls._clean_html(title)
            if not title:
                continue

            # Summary
            summary = content.get("summary") or content.get("description") or item.get("summary", "")
            summary = cls._clean_html(summary)

            # Link
            raw_url = (
                _as_dict(content.get("canonicalUrl")).get("url")
                or _as_dict(content.get("clickThroughUrl")).get("url")
                or item.get("link")
                or f"https://finance.yahoo.com/quote/{yf_ticker}"
            )
            canonical_url = cls.canonicalize_url(raw_url) or raw_url

            # Publisher: Real provider displayName as publisher
            provider_dict = _as_dict(item.get("provider"))
            content_provider = _as_dict(content.get("provider"))
            raw_publisher = (
                provider_dict.get("displayName")
                or content_provider.get("displayName")
                or item.get("publisher")
                or "Yahoo Finance"
            )
            publisher = str(raw_publisher or "").strip()

            # Timestamp: Never default to now()
            pub_time: datetime | None = None
            pub_date_str = content.get("pubDate") or item.get("pubDate")
            if pub_date_str and isinstance(pub_date_str, str):
                try:
                    pub_time = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                    if pub_time.tzinfo is None:
                        pub_time = pub_time.replace(tzinfo=timezone.utc)
                except Exception:
                    pub_time = None

            if pub_time is None:
                pub_ts = item.get("providerPublishTime") or content.get("providerPublishTime")
                if pub_ts is not None:
                    try:
                        pub_time = datetime.fromtimestamp(float(pub_ts), tz=timezone.utc)
                    except Exception:
                        pub_time = None

            art_id = cls._create_article_id(canonical_url, title)
            articles.append(
                IngestedArticle(
                    article_id=art_id,
                    provider=ProviderType.YFINANCE,
                    source_name=f"Yahoo - {publisher}" if publisher else "Yahoo Finance",
                    canonical_url=canonical_url,
                    title=title,
                    summary=summary[:1000] if summary else "",
                    published_at_utc=pub_time,
                    retrieved_at_utc=now,
                    raw_provider_metadata={"yf_publisher": publisher},
                )
            )

        return articles

    @classmethod
    def parse_rss_feed_content(
        cls,
        feed_content: str | bytes,
        default_source_name: str,
        provider: ProviderType,
        publisher_is_authoritative: bool = False,
    ) -> list[IngestedArticle]:
        """
        Parses an RSS feed from a string/bytes payload.
        Published time comes from published_parsed, otherwise None.
        Extracts source from entry.source.title; if absent:
        - if publisher_is_authoritative is True (direct feeds like FXStreet, Investing.com),
          falls back to default_source_name with publisher_inferred = False.
        - otherwise (e.g. Google News aggregators), sets publisher_inferred = True.
        """
        feed = feedparser.parse(feed_content)
        articles: list[IngestedArticle] = []
        now = datetime.now(timezone.utc)

        for entry in getattr(feed, "entries", []):
            raw_title = getattr(entry, "title", "")
            raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            link = getattr(entry, "link", "")
            canonical_url = cls.canonicalize_url(link) or link

            # Publisher from entry.source.title
            publisher = ""
            inferred = False
            source_obj = getattr(entry, "source", None)
            if source_obj:
                if isinstance(source_obj, dict):
                    publisher = (source_obj.get("title") or source_obj.get("value") or "").strip()
                else:
                    publisher = (getattr(source_obj, "title", "") or getattr(source_obj, "value", "") or "").strip()

            if not publisher:
                publisher = default_source_name
                if not publisher_is_authoritative:
                    inferred = True

            title = cls._clean_entry_title(raw_title, publisher)
            if not title:
                continue

            summary = cls._clean_entry_summary(raw_summary, title, publisher)

            # Publication time
            pub_time: datetime | None = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pub_time = None

            raw_meta: dict = {
                "rss_source": default_source_name,
                "publisher": publisher,
                "publisher_inferred": inferred,
            }

            art_id = cls._create_article_id(canonical_url, title)
            articles.append(
                IngestedArticle(
                    article_id=art_id,
                    provider=provider,
                    source_name=publisher,
                    canonical_url=canonical_url,
                    title=title,
                    summary=summary,
                    published_at_utc=pub_time,
                    retrieved_at_utc=now,
                    raw_provider_metadata=raw_meta,
                )
            )

        return articles

    @classmethod
    def _fetch_yfinance_news_sync(cls, yf_ticker: str, count: int = 50) -> list[IngestedArticle]:
        """Fetches recent news articles from yfinance API synchronously with count parameter support."""
        ticker_obj = yf.Ticker(yf_ticker)
        news_items = None
        get_news_fn = getattr(ticker_obj, "get_news", None)
        if callable(get_news_fn):
            try:
                res = ticker_obj.get_news(count=count)
                if isinstance(res, list):
                    news_items = res
            except TypeError:
                pass
            except Exception as e:
                logger.warning(f"Error calling get_news on yfinance for {yf_ticker}: {e}")

        if news_items is None:
            news_items = getattr(ticker_obj, "news", [])

        if not isinstance(news_items, list):
            return []
        return cls.parse_yfinance_items(news_items, yf_ticker)

    @classmethod
    def _fetch_feed_httpx_sync(
        cls,
        url: str,
        default_source_name: str,
        provider: ProviderType,
        publisher_is_authoritative: bool = False,
    ) -> list[IngestedArticle]:
        """
        Fetches an RSS feed via httpx synchronously with per-provider timeouts.
        Rejects non-feed HTML 200 responses as ValueError('NOT_A_FEED').
        """
        timeout = httpx.Timeout(8.0, connect=4.0)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type and not any(t in content_type for t in ("xml", "rss", "atom")):
                raise ValueError("NOT_A_FEED")

            content = resp.content
            feed = feedparser.parse(content)
            version = getattr(feed, "version", "") or ""
            entries = getattr(feed, "entries", []) or []
            if not version and not entries:
                raise ValueError("NOT_A_FEED")

            return cls.parse_rss_feed_content(
                content,
                default_source_name,
                provider,
                publisher_is_authoritative=publisher_is_authoritative,
            )

    @classmethod
    async def _fetch_feed_httpx_async(
        cls,
        client: httpx.AsyncClient,
        spec: FeedSpec,
    ) -> list[IngestedArticle]:
        """
        Fetches an RSS feed asynchronously with tenacity retry (jitter on 429/5xx/timeouts).
        Rejects non-feed HTML 200 responses as ValueError('NOT_A_FEED').
        """
        attempt_count = 0

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(settings.FEED_RETRY_ATTEMPTS),
            wait=tenacity.wait_random_exponential(multiplier=0.1, max=1.0),
            retry=tenacity.retry_if_exception(lambda exc: cls._should_retry_feed(exc)),
            reraise=True,
        )
        async def _do_get():
            nonlocal attempt_count
            attempt_count += 1
            resp = await client.get(spec.url)
            if resp.status_code == 429 or resp.status_code >= 500:
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type and not any(t in content_type for t in ("xml", "rss", "atom")):
                raise ValueError("NOT_A_FEED")

            content = resp.content
            feed = feedparser.parse(content)
            version = getattr(feed, "version", "") or ""
            entries = getattr(feed, "entries", []) or []
            if not version and not entries:
                raise ValueError("NOT_A_FEED")

            return cls.parse_rss_feed_content(
                content,
                default_source_name=spec.publisher,
                provider=spec.provider_type,
                publisher_is_authoritative=spec.publisher_is_authoritative,
            )

        return await _do_get()

    @staticmethod
    def _should_retry_feed(exc: BaseException) -> bool:
        if isinstance(exc, ValueError) and "NOT_A_FEED" in str(exc):
            return False
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code == 429 or exc.response.status_code >= 500
        if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
            return True
        return False

    @classmethod
    def build_feed_specs(
        cls,
        ticker: str,
        company_name: str,
        session: SessionWindow,
        asset_type: AssetType = AssetType.EQUITY,
        yf_symbol: str = "",
    ) -> list[FeedSpec]:
        """Constructs feed specifications for direct forex and Google News sweeps."""
        yf_ticker = yf_symbol or ticker
        specs: list[FeedSpec] = []

        # 1. Dedicated Forex / Commodity feeds
        if asset_type in (AssetType.FOREX, AssetType.COMMODITY) or "/" in ticker or "=X" in yf_ticker:
            specs.append(
                FeedSpec(
                    key="forex_investing_com_forex",
                    kind=ProviderKind.RSS_DIRECT,
                    url="https://www.investing.com/rss/news_1.rss",
                    publisher="Investing.com Forex",
                    provider_type=ProviderType.INVESTING_FOREX_RSS,
                    publisher_is_authoritative=True,
                )
            )
            specs.append(
                FeedSpec(
                    key="forex_fxstreet",
                    kind=ProviderKind.RSS_DIRECT,
                    url="https://www.fxstreet.com/rss/news",
                    publisher="FXStreet",
                    provider_type=ProviderType.FXSTREET_RSS,
                    publisher_is_authoritative=True,
                )
            )
            specs.append(
                FeedSpec(
                    key="forex_yahoo_finance_forex_rss",
                    kind=ProviderKind.RSS_DIRECT,
                    url=f"https://finance.yahoo.com/rss/headline?s={yf_ticker}",
                    publisher="Yahoo Finance Forex RSS",
                    provider_type=ProviderType.YFINANCE,
                    publisher_is_authoritative=False,
                )
            )

        # 2. Google News RSS sweeps
        lookback_hours = session.window_duration_hours if session else 24.0
        n_hours = min(72, max(1, math.ceil(lookback_hours) + 1))
        when_tag = f"when:{n_hours}h"
        base_query = build_google_query_subject(ticker, company_name, asset_type)

        domain_map = (
            FOREX_COMMODITY_PUBLISHER_DOMAINS
            if asset_type in (AssetType.FOREX, AssetType.COMMODITY)
            else EQUITY_PUBLISHER_DOMAINS
        )

        gen_query = f"{base_query} {when_tag}"
        encoded_gen = urllib.parse.quote_plus(gen_query)
        gen_url = f"https://news.google.com/rss/search?q={encoded_gen}&hl=en-US&gl=US&ceid=US:en"
        specs.append(
            FeedSpec(
                key="rss_google_news_general",
                kind=ProviderKind.RSS_GOOGLE,
                url=gen_url,
                publisher="Google News",
                provider_type=ProviderType.GOOGLE_RSS_AGGREGATOR,
                publisher_is_authoritative=False,
            )
        )

        for pub_name, domain in domain_map.items():
            sweep_query = f"{base_query} site:{domain} {when_tag}"
            encoded_sweep = urllib.parse.quote_plus(sweep_query)
            sweep_url = f"https://news.google.com/rss/search?q={encoded_sweep}&hl=en-US&gl=US&ceid=US:en"
            key = f"rss_{pub_name.lower().replace(' ', '_').replace('.', '_')}"
            specs.append(
                FeedSpec(
                    key=key,
                    kind=ProviderKind.RSS_GOOGLE,
                    url=sweep_url,
                    publisher=pub_name,
                    provider_type=ProviderType.GOOGLE_RSS_AGGREGATOR,
                    publisher_is_authoritative=False,
                )
            )

        return specs

    @classmethod
    async def fetch_news_for_session(
        cls,
        ticker: str,
        company_name: str,
        session: SessionWindow,
        asset_type: AssetType = AssetType.EQUITY,
        yf_symbol: str = "",
        http_client: httpx.AsyncClient | None = None,
        io_executor: Any = None,
    ) -> tuple[list[IngestedArticle], ProviderOutcomeList]:
        """
        Concurrent multi-source news ingestion bounded to current session lookback:
        1. Starts Yahoo (get_news(count=YF_NEWS_COUNT) on io_executor) and all feeds concurrently.
        2. asyncio.wait(tasks, timeout=settings.INGESTION_TIMEOUT_SECONDS) keeps partial results.
        3. Stragglers marked TIMEOUT.
        4. Ingestion drops only exact duplicates (same article_id).
        """
        yf_ticker = yf_symbol or ticker
        feed_specs = cls.build_feed_specs(ticker, company_name, session, asset_type, yf_symbol)

        async def _execute_sweep(client: httpx.AsyncClient) -> tuple[list[IngestedArticle], ProviderOutcomeList]:
            loop = asyncio.get_running_loop()
            t0 = time.time()

            # 1. Yahoo Finance task on I/O executor
            t_yf = time.time()

            async def _run_yf():
                return await loop.run_in_executor(
                    io_executor,
                    cls._fetch_yfinance_news_sync,
                    yf_ticker,
                    settings.YF_NEWS_COUNT,
                )

            yf_task = asyncio.create_task(_run_yf())

            # 2. Feed tasks
            feed_tasks: dict[asyncio.Task, tuple[FeedSpec, float]] = {}
            for spec in feed_specs:
                async def _run_feed(s=spec):
                    if isinstance(cls._fetch_feed_httpx_sync, MagicMock):
                        return cls._fetch_feed_httpx_sync(
                            s.url, s.publisher, s.provider_type, s.publisher_is_authoritative
                        )
                    return await cls._fetch_feed_httpx_async(client, s)

                task = asyncio.create_task(_run_feed())
                feed_tasks[task] = (spec, time.time())

            # All tasks start together before any completes
            all_tasks = {yf_task} | set(feed_tasks.keys())
            done, pending = await asyncio.wait(all_tasks, timeout=settings.INGESTION_TIMEOUT_SECONDS)

            collected_articles: list[IngestedArticle] = []
            outcomes: list[ProviderOutcome] = []

            # Evaluate Yahoo Finance
            if yf_task in done:
                exc = yf_task.exception()
                lat = round((time.time() - t_yf) * 1000, 1)
                if exc is None:
                    yf_items = yf_task.result() or []
                    collected_articles.extend(yf_items)
                    outcomes.append(
                        ProviderOutcome(
                            key="yfinance",
                            kind=ProviderKind.YFINANCE,
                            status="SUCCESS",
                            count=len(yf_items),
                            latency_ms=lat,
                        )
                    )
                else:
                    logger.warning(f"Error fetching yfinance news for {yf_ticker}: {exc}")
                    outcomes.append(
                        ProviderOutcome(
                            key="yfinance",
                            kind=ProviderKind.YFINANCE,
                            status="FAILED",
                            count=0,
                            latency_ms=lat,
                            error_code=str(exc),
                        )
                    )
            else:
                yf_task.cancel()
                logger.warning(f"Yahoo Finance ingestion timed out for {yf_ticker}")
                outcomes.append(
                    ProviderOutcome(
                        key="yfinance",
                        kind=ProviderKind.YFINANCE,
                        status="TIMEOUT",
                        count=0,
                        latency_ms=round(settings.INGESTION_TIMEOUT_SECONDS * 1000, 1),
                        error_code="TIMEOUT",
                    )
                )

            # Evaluate feeds
            for task, (spec, t_spec) in feed_tasks.items():
                lat = round((time.time() - t_spec) * 1000, 1)
                if task in done:
                    exc = task.exception()
                    if exc is None:
                        items = task.result() or []
                        collected_articles.extend(items)
                        outcomes.append(
                            ProviderOutcome(
                                key=spec.key,
                                kind=spec.kind,
                                status="SUCCESS",
                                count=len(items),
                                latency_ms=lat,
                            )
                        )
                    else:
                        err_code = "NOT_A_FEED" if "NOT_A_FEED" in str(exc) else str(exc)
                        logger.warning(f"Feed {spec.key} ({spec.publisher}) failed: {exc}")
                        outcomes.append(
                            ProviderOutcome(
                                key=spec.key,
                                kind=spec.kind,
                                status="FAILED",
                                count=0,
                                latency_ms=lat,
                                error_code=err_code,
                            )
                        )
                else:
                    task.cancel()
                    logger.warning(
                        f"Feed {spec.key} ({spec.publisher}) timed out after {settings.INGESTION_TIMEOUT_SECONDS}s"
                    )
                    outcomes.append(
                        ProviderOutcome(
                            key=spec.key,
                            kind=spec.kind,
                            status="TIMEOUT",
                            count=0,
                            latency_ms=round(settings.INGESTION_TIMEOUT_SECONDS * 1000, 1),
                            error_code="TIMEOUT",
                        )
                    )

            # Ingestion only drops exact duplicates (same article_id)
            seen_ids = set()
            all_articles: list[IngestedArticle] = []
            for art in collected_articles:
                if art.article_id in seen_ids:
                    continue
                seen_ids.add(art.article_id)
                all_articles.append(art)

            outcome_list = ProviderOutcomeList(outcomes)
            logger.info(
                f"Ingestion sweep completed for {ticker} ({asset_type.value}): "
                f"{len(all_articles)} unique headlines ingested across {len(outcome_list)} providers in {round((time.time() - t0)*1000, 1)}ms."
            )
            return all_articles, outcome_list

        if http_client is not None:
            return await _execute_sweep(http_client)

        timeout = httpx.Timeout(8.0, connect=4.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": settings.HTTP_USER_AGENT},
            follow_redirects=True,
        ) as client:
            return await _execute_sweep(client)
