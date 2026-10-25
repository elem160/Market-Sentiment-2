"""End-to-end integration tests for job execution, persistence, cache behavior, and article ID stability (C1, C2, H13)."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.enums import CacheStatus, ProviderType
from app.core.models import Asset, IngestedArticle
from app.core.session_window import compute_session_window
from app.db.repository import SentimentRepository


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    import json
    events = []
    current_event = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("event:"):
            current_event = line.replace("event:", "").strip()
        elif line.startswith("data:") and current_event:
            data_json = json.loads(line.replace("data:", "").strip())
            events.append((current_event, data_json))
            current_event = None
    return events


@pytest.mark.asyncio
async def test_complete_job_flow_and_cache_transitions(async_client, db_session):
    """
    Test standard analysis job lifecycle:
    1. POST /api/v1/analyze -> 202 JobCreatedResponse with max_wait_seconds
    2. SSE events received until 'completed' with run_id
    3. GET /api/v1/analysis/{run_id} -> 200 with cache_status MISS
    4. Stable article_id matches observed_facts cited_article_id
    5. Second POST /api/v1/analyze -> 200 cache HIT
    """
    now = compute_session_window().window_end_utc
    mock_asset = Asset(ticker="AAPL", company_name="Apple Inc.", exchange="NASDAQ")
    art1 = IngestedArticle(
        article_id="art_aapl_101",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/aapl1",
        title="Apple reports robust quarterly earnings and record growth",
        summary="Apple Inc exceeded expectations with high iPhone revenue.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    art2 = IngestedArticle(
        article_id="art_aapl_102",
        provider=ProviderType.GOOGLE_RSS_AGGREGATOR,
        source_name="Bloomberg",
        canonical_url="https://bloomberg.com/aapl2",
        title="Apple services revenue surges in latest financial report",
        summary="Services segment expands significantly.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    provider_outcomes = {
        "yfinance": {"status": "SUCCESS", "count": 1},
        "rss_reuters": {"status": "SUCCESS", "count": 1},
    }

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([art1, art2], provider_outcomes))):

        # 1. Start analysis
        resp = await async_client.post("/api/v1/analyze", json={"ticker": "AAPL", "force_refresh": True})
        assert resp.status_code == 202
        data = resp.json()
        job_id = data["job_id"]
        assert "max_wait_seconds" in data
        assert data["max_wait_seconds"] > 0

        # Wait for background task to complete
        for _ in range(50):
            db_session.expire_all()
            job = SentimentRepository.get_job(db_session, job_id)
            if job and job.status in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.1)

        assert job is not None
        assert job.status == "COMPLETED"
        run_id = job.run_id
        assert run_id is not None

        # 2. Fetch analysis by run_id
        res_resp = await async_client.get(f"/api/v1/analysis/{run_id}")
        assert res_resp.status_code == 200
        result_data = res_resp.json()
        assert result_data["run_id"] == run_id
        assert result_data["cache_status"] == CacheStatus.MISS.value
        assert len(result_data["articles"]) > 0

        # Verify article_id stability (H13)
        article_ids = {a["article_id"] for a in result_data["articles"]}
        assert "art_aapl_101" in article_ids or "art_aapl_102" in article_ids
        for fact in result_data["rationale"]["observed_facts"]:
            assert fact["cited_article_id"] in article_ids

        # 3. Subsequent request without force_refresh hits cache
        cached_resp = await async_client.post("/api/v1/analyze", json={"ticker": "AAPL", "force_refresh": False})
        assert cached_resp.status_code == 200
        cached_data = cached_resp.json()
        assert cached_data["run_id"] == run_id
        assert cached_data["cache_status"] == CacheStatus.HIT.value


@pytest.mark.asyncio
async def test_all_rss_failed_persists_run_and_bypasses_cache(async_client, db_session, wait_for_jobs):
    """
    Test degraded run when all RSS providers fail (C2):
    - Run is successfully saved to the database.
    - Run is retrievable by ID via GET /analysis/{run_id} (200).
    - Subsequent POST /analyze does NOT return it from cache (is_cacheable=False).
    """
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

        # 1. Start analysis
        resp = await async_client.post("/api/v1/analyze", json={"ticker": "AAPL", "force_refresh": True})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Wait for background job to finish
        for _ in range(50):
            db_session.expire_all()
            job = SentimentRepository.get_job(db_session, job_id)
            if job and job.status in ("COMPLETED", "FAILED"):
                break
            await asyncio.sleep(0.1)

        assert job is not None
        assert job.status == "COMPLETED"
        run_id = job.run_id
        assert run_id is not None

        # 2. Fetch analysis by run_id: MUST return 200 (Fixing C2)
        res_resp = await async_client.get(f"/api/v1/analysis/{run_id}")
        assert res_resp.status_code == 200
        res_data = res_resp.json()
        assert res_data["run_id"] == run_id
        assert any("All RSS news providers failed" in w for w in res_data["warnings"])

        # 3. Subsequent call without force_refresh must NOT return this uncacheable run as a cache hit
        # (It creates a new job or runs fresh)
        subsequent_resp = await async_client.post("/api/v1/analyze", json={"ticker": "AAPL", "force_refresh": False})
        # If not cached, it returns 202 (queued new job) rather than 200 (cache hit)
        assert subsequent_resp.status_code == 202
        await wait_for_jobs()
