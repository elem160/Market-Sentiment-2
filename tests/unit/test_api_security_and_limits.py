import time
import pytest
from unittest.mock import MagicMock
from fastapi import Request
from app.config import settings
from app.utils.rate_limiter import SlidingWindowRateLimiter
from app.core.exceptions import RateLimitExceededException
from app.api.dependencies import get_client_ip


def test_rate_limiter_prunes_stale_keys_preventing_leak():
    """Verify F-15: Rate limiter prunes stale keys and does not grow unboundedly."""
    limiter = SlidingWindowRateLimiter()

    # Fill limiter with 60 distinct IP keys in the past
    now = time.time()
    for i in range(60):
        key = f"192.168.1.{i}"
        limiter._requests[key] = [now - 120.0]  # Timestamps older than 60s window

    assert len(limiter._requests) == 60

    # Making a check triggers periodic pruning when dict size > 50
    limiter.check("10.0.0.1", max_requests=10, window_seconds=60)

    # All stale keys should have been purged, leaving only the active key
    assert len(limiter._requests) == 1
    assert "10.0.0.1" in limiter._requests


def test_rate_limiter_enforces_limit():
    """Verify rate limiter raises RateLimitExceededException when max_requests exceeded."""
    limiter = SlidingWindowRateLimiter()
    for _ in range(5):
        assert limiter.check("127.0.0.1", max_requests=5, window_seconds=60) is True

    with pytest.raises(RateLimitExceededException) as exc_info:
        limiter.check("127.0.0.1", max_requests=5, window_seconds=60)
    assert exc_info.value.status_code == 429


def test_get_client_ip_proxy_trust():
    """Verify F-17: X-Forwarded-For is only trusted when TRUST_PROXY_HEADERS is True."""
    # Mock Request
    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "203.0.113.195, 70.41.3.18"}
    req.client = MagicMock()
    req.client.host = "198.51.100.1"

    # Default: TRUST_PROXY_HEADERS = False -> ignore X-Forwarded-For
    try:
        settings.TRUST_PROXY_HEADERS = False
        assert get_client_ip(req) == "198.51.100.1"

        # Explicitly enabled: TRUST_PROXY_HEADERS = True -> use first IP from X-Forwarded-For
        settings.TRUST_PROXY_HEADERS = True
        assert get_client_ip(req) == "203.0.113.195"
    finally:
        settings.TRUST_PROXY_HEADERS = False
