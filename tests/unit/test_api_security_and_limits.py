import time
from unittest.mock import MagicMock
import pytest
from fastapi import Request
from app.config import settings
from app.utils.rate_limiter import SlidingWindowRateLimiter
from app.core.exceptions import RateLimitExceededException
from app.api.dependencies import get_client_ip, is_ip_trusted


def test_rate_limiter_bounded_lru_cap():
    """Verify H12/L6: Rate limiter caps tracked keys at max_keys and evicts LRU keys."""
    limiter = SlidingWindowRateLimiter(max_keys=50)

    # Fill limiter with 60 distinct IP keys
    now = time.time()
    for i in range(60):
        limiter.check("analyze", f"192.168.1.{i}", max_requests=10, window_seconds=60)

    assert limiter.total_tracked_keys == 50
    # Oldest keys (0..9) should have been evicted by LRU
    assert ("analyze", "192.168.1.0") not in limiter._store
    assert ("analyze", "192.168.1.59") in limiter._store


def test_rate_limiter_enforces_limit():
    """Verify rate limiter raises RateLimitExceededException when max_requests exceeded."""
    limiter = SlidingWindowRateLimiter()
    for _ in range(5):
        assert limiter.check("analyze", "127.0.0.1", max_requests=5, window_seconds=60) is True

    with pytest.raises(RateLimitExceededException) as exc_info:
        limiter.check("analyze", "127.0.0.1", max_requests=5, window_seconds=60)
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after_seconds > 0


def test_get_client_ip_proxy_trust():
    """Verify H12: X-Forwarded-For is only trusted when direct peer is in TRUSTED_PROXY_IPS."""
    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "203.0.113.195, 70.41.3.18"}
    req.client = MagicMock()
    req.client.host = "10.0.0.1"

    original_trust = settings.TRUST_PROXY_HEADERS
    original_trusted_ips = settings.TRUSTED_PROXY_IPS
    try:
        # Default: TRUST_PROXY_HEADERS = False -> ignore X-Forwarded-For
        settings.TRUST_PROXY_HEADERS = False
        settings.TRUSTED_PROXY_IPS = ["10.0.0.1"]
        assert get_client_ip(req) == "10.0.0.1"

        # Explicitly enabled and peer trusted -> rightmost untrusted hop
        settings.TRUST_PROXY_HEADERS = True
        assert get_client_ip(req) == "70.41.3.18"

        # Untrusted direct peer -> ignores X-Forwarded-For header
        req.client.host = "198.51.100.1"
        assert get_client_ip(req) == "198.51.100.1"
    finally:
        settings.TRUST_PROXY_HEADERS = original_trust
        settings.TRUSTED_PROXY_IPS = original_trusted_ips


def test_is_ip_trusted_cidr_and_exact():
    """Verify CIDR and exact IP matching for trusted proxies."""
    trusted = ["127.0.0.1", "10.0.0.0/8", "192.168.1.0/24", "::1"]
    assert is_ip_trusted("127.0.0.1", trusted) is True
    assert is_ip_trusted("10.50.2.1", trusted) is True
    assert is_ip_trusted("192.168.1.42", trusted) is True
    assert is_ip_trusted("::1", trusted) is True
    assert is_ip_trusted("192.168.2.1", trusted) is False
    assert is_ip_trusted("8.8.8.8", trusted) is False
    assert is_ip_trusted("invalid-ip", trusted) is False
