import math
import time
from collections import OrderedDict
from app.core.exceptions import RateLimitExceededException


class SlidingWindowRateLimiter:
    """
    In-memory scoped sliding window rate limiter with bounded LRU key store.
    - Scopes: 'analyze', 'jobs', 'read'
    - Bounded capacity: strictly capped at max_keys (10,000) using OrderedDict LRU eviction
    - Precision retry_after calculation for HTTP 429 Retry-After headers
    """

    def __init__(self, max_keys: int = 10000):
        self.max_keys = max_keys
        # (scope, key) -> list[float timestamps]
        self._store: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

    def check(
        self,
        scope_or_key: str,
        key_or_max: str | int | None = None,
        max_requests: int = 15,
        window_seconds: int = 60,
    ) -> bool:
        """
        Check rate limit for (scope, key).
        Supports two calling signatures:
        1. check(scope: str, key: str, max_requests: int, window_seconds: int = 60)
        2. check(key: str, max_requests: int = 15, window_seconds: int = 60) [backward compatible]
        """
        if isinstance(key_or_max, str):
            scope = scope_or_key
            key = key_or_max
            limit = max_requests
            window = window_seconds
        else:
            scope = "default"
            key = scope_or_key
            limit = key_or_max if isinstance(key_or_max, int) else max_requests
            window = window_seconds

        composite_key = (scope, key)
        now = time.time()
        cutoff = now - window

        if composite_key in self._store:
            # Move to end for LRU tracking
            self._store.move_to_end(composite_key)
            timestamps = [t for t in self._store[composite_key] if t > cutoff]
        else:
            timestamps = []

        if len(timestamps) >= limit:
            oldest_in_window = timestamps[0]
            elapsed = now - oldest_in_window
            retry_after = max(1, min(window, math.ceil(window - elapsed)))
            self._store[composite_key] = timestamps
            raise RateLimitExceededException(retry_after_seconds=retry_after)

        timestamps.append(now)
        self._store[composite_key] = timestamps

        # Bounded LRU eviction
        while len(self._store) > self.max_keys:
            self._store.popitem(last=False)

        return True

    def reset(self):
        """Clear all in-memory rate limit records."""
        self._store.clear()

    @property
    def total_tracked_keys(self) -> int:
        """Return total active tracked composite keys."""
        return len(self._store)


rate_limiter = SlidingWindowRateLimiter()
