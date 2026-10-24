from unittest.mock import MagicMock, patch
import pytest
from starlette.requests import Request
from app.api.dependencies import get_client_ip
from app.config import settings
from app.core.exceptions import RateLimitExceededException
from app.utils.rate_limiter import SlidingWindowRateLimiter, rate_limiter


def test_rate_limiter_lru_cap_holds():
    """Verify H12: LRU key store is strictly bounded at max_keys (10,000 default)."""
    limiter = SlidingWindowRateLimiter(max_keys=100)

    for i in range(150):
        limiter.check("analyze", f"client_{i}", max_requests=10, window_seconds=60)

    assert limiter.total_tracked_keys == 100
    # Oldest 50 keys (client_0 .. client_49) were evicted
    assert ("analyze", "client_0") not in limiter._store
    assert ("analyze", "client_49") not in limiter._store
    # Latest keys remain
    assert ("analyze", "client_50") in limiter._store
    assert ("analyze", "client_149") in limiter._store


def test_spoofed_leftmost_xff_is_ignored():
    """Verify H12: Leftmost client-spoofed XFF entries are ignored; first untrusted from right is used."""
    req = MagicMock(spec=Request)
    # Attacker at 198.51.100.99 sends spoofed header XFF: 8.8.8.8, which proxy forwards as:
    req.headers = {"x-forwarded-for": "8.8.8.8, 198.51.100.99"}
    req.client = MagicMock()
    req.client.host = "10.0.0.1"

    original_trust = settings.TRUST_PROXY_HEADERS
    original_proxies = settings.TRUSTED_PROXY_IPS
    try:
        settings.TRUST_PROXY_HEADERS = True
        settings.TRUSTED_PROXY_IPS = ["10.0.0.1"]

        resolved = get_client_ip(req)
        # Must resolve to 198.51.100.99, not the spoofed 8.8.8.8
        assert resolved == "198.51.100.99"
    finally:
        settings.TRUST_PROXY_HEADERS = original_trust
        settings.TRUSTED_PROXY_IPS = original_proxies


def test_trusted_proxy_chain_resolves():
    """Verify H12: Walking multiple trusted proxies in XFF correctly identifies the origin client."""
    req = MagicMock(spec=Request)
    # Hop chain: Genuine Client (203.0.113.4) -> Edge CDN (172.16.5.1) -> Ingress Proxy (10.0.0.2)
    req.headers = {"x-forwarded-for": "203.0.113.4, 172.16.5.1"}
    req.client = MagicMock()
    req.client.host = "10.0.0.2"

    original_trust = settings.TRUST_PROXY_HEADERS
    original_proxies = settings.TRUSTED_PROXY_IPS
    try:
        settings.TRUST_PROXY_HEADERS = True
        settings.TRUSTED_PROXY_IPS = ["10.0.0.0/8", "172.16.0.0/12"]

        resolved = get_client_ip(req)
        assert resolved == "203.0.113.4"
    finally:
        settings.TRUST_PROXY_HEADERS = original_trust
        settings.TRUSTED_PROXY_IPS = original_proxies


def test_untrusted_direct_peer_ignores_xff():
    """Verify H12: If direct peer is not in TRUSTED_PROXY_IPS, X-Forwarded-For is ignored completely."""
    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "1.2.3.4"}
    req.client = MagicMock()
    req.client.host = "198.51.100.55"  # Public untrusted address

    original_trust = settings.TRUST_PROXY_HEADERS
    original_proxies = settings.TRUSTED_PROXY_IPS
    try:
        settings.TRUST_PROXY_HEADERS = True
        settings.TRUSTED_PROXY_IPS = ["10.0.0.1"]

        resolved = get_client_ip(req)
        assert resolved == "198.51.100.55"
    finally:
        settings.TRUST_PROXY_HEADERS = original_trust
        settings.TRUSTED_PROXY_IPS = original_proxies


@pytest.mark.asyncio
async def test_job_polls_do_not_block_analyze(async_client, db_session):
    """Verify H12: 15 job status polls in 'jobs' scope do not consume capacity for 'analyze' scope."""
    rate_limiter.reset()
    from app.db.repository import SentimentRepository
    SentimentRepository.create_job(db_session, "test-poll-job", "AAPL")

    # 1. Execute 15 polls on /jobs/{id}
    for _ in range(15):
        resp = await async_client.get("/api/v1/jobs/test-poll-job")
        assert resp.status_code == 200

    # 2. Verify /analyze is NOT rate limited and still succeeds
    with patch("app.services.ticker_service.TickerService.resolve_ticker_async") as mock_resolve, \
         patch("app.services.job_manager.JobManager._run_job"):
        from app.core.models import Asset
        from app.core.enums import AssetType
        mock_resolve.return_value = Asset(
            ticker="AAPL",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            asset_type=AssetType.EQUITY,
            is_active=True,
        )
        analyze_resp = await async_client.post(
            "/api/v1/analyze",
            json={"ticker": "AAPL", "force_refresh": True, "enable_llm": False},
        )
        assert analyze_resp.status_code == 202


@pytest.mark.asyncio
async def test_retry_after_header_present_on_429(async_client, db_session):
    """Verify H12: Exceeding rate limit yields 429 response carrying Retry-After header."""
    rate_limiter.reset()

    # Analyze limit is 15 req/min
    with patch("app.services.ticker_service.TickerService.resolve_ticker_async") as mock_resolve, \
         patch("app.services.job_manager.JobManager._run_job"):
        from app.core.models import Asset
        from app.core.enums import AssetType
        mock_resolve.return_value = Asset(
            ticker="AAPL",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            asset_type=AssetType.EQUITY,
            is_active=True,
        )

        for _ in range(settings.RATE_LIMIT_ANALYSIS_PER_MINUTE):
            resp = await async_client.post(
                "/api/v1/analyze",
                json={"ticker": "AAPL", "force_refresh": True, "enable_llm": False},
            )
            assert resp.status_code == 202

        # 16th request must trigger 429 with Retry-After header
        blocked_resp = await async_client.post(
            "/api/v1/analyze",
            json={"ticker": "AAPL", "force_refresh": True, "enable_llm": False},
        )
        assert blocked_resp.status_code == 429
        assert "retry-after" in blocked_resp.headers
        retry_val = int(blocked_resp.headers["retry-after"])
        assert 1 <= retry_val <= 60

        data = blocked_resp.json()
        assert data["error"] == "RateLimitExceededException"
        assert "retry_after_seconds" in data["details"]


@pytest.mark.asyncio
async def test_read_scope_rate_limiting(async_client, db_session):
    """Verify H12: /history endpoint is rate limited under 'read' scope."""
    rate_limiter.reset()

    # Exhaust read rate limit (RATE_LIMIT_READ_PER_MINUTE)
    for _ in range(settings.RATE_LIMIT_READ_PER_MINUTE):
        rate_limiter.check("read", "127.0.0.1", max_requests=settings.RATE_LIMIT_READ_PER_MINUTE)

    # Next /history request must return 429
    resp = await async_client.get("/api/v1/history")
    assert resp.status_code == 429
    assert "retry-after" in resp.headers
