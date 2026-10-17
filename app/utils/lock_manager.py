import asyncio


class TickerLockManager:
    """In-memory per-ticker asyncio lock manager for request coalescing."""
    _locks: dict[str, asyncio.Lock] = {}
    _master_lock: asyncio.Lock = asyncio.Lock()

    @classmethod
    async def get_lock(cls, ticker: str) -> asyncio.Lock:
        normalized = ticker.upper().strip()
        async with cls._master_lock:
            if normalized not in cls._locks:
                cls._locks[normalized] = asyncio.Lock()
            return cls._locks[normalized]
