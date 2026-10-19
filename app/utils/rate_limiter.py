import time
from collections import defaultdict
from app.core.exceptions import RateLimitExceededException


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter keyed by client IP."""
    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int = 15, window_seconds: int = 60) -> bool:
        now = time.time()
        cutoff = now - window_seconds
        
        # Prune old timestamps for active key
        timestamps = [t for t in self._requests[key] if t > cutoff]
        if timestamps:
            self._requests[key] = timestamps
        elif key in self._requests:
            del self._requests[key]

        # Prune stale keys across the map periodically to prevent memory leaks (F-15)
        if len(self._requests) > 50:
            stale_keys = [k for k, ts in self._requests.items() if not ts or ts[-1] <= cutoff]
            for k in stale_keys:
                self._requests.pop(k, None)

        if len(timestamps) >= max_requests:
            oldest_in_window = timestamps[0]
            retry_after = int(window_seconds - (now - oldest_in_window)) + 1
            raise RateLimitExceededException(retry_after_seconds=max(1, retry_after))

        self._requests[key].append(now)
        return True

    def reset(self):
        """Clear all in-memory rate limit records."""
        self._requests.clear()


rate_limiter = SlidingWindowRateLimiter()
