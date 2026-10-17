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
        
        # Prune old timestamps
        timestamps = [t for t in self._requests[key] if t > cutoff]
        self._requests[key] = timestamps

        if len(timestamps) >= max_requests:
            oldest_in_window = timestamps[0]
            retry_after = int(window_seconds - (now - oldest_in_window)) + 1
            raise RateLimitExceededException(retry_after_seconds=max(1, retry_after))

        self._requests[key].append(now)
        return True


rate_limiter = SlidingWindowRateLimiter()
