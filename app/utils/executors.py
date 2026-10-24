import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

from app.db.database import SessionLocal

T = TypeVar("T")

_db_executor: ThreadPoolExecutor | None = None
_io_executor: ThreadPoolExecutor | None = None


def get_db_executor() -> ThreadPoolExecutor:
    """Return the shared 4-thread executor for database operations."""
    global _db_executor
    if _db_executor is None:
        _db_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="db_pool")
    return _db_executor


def get_io_executor() -> ThreadPoolExecutor:
    """Return the shared 4-thread executor for blocking I/O (e.g. yfinance)."""
    global _io_executor
    if _io_executor is None:
        _io_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="io_pool")
    return _io_executor


def shutdown_executors() -> None:
    """Gracefully shut down the DB and I/O worker pools upon application shutdown."""
    global _db_executor, _io_executor
    if _db_executor is not None:
        _db_executor.shutdown(wait=False)
        _db_executor = None
    if _io_executor is not None:
        _io_executor.shutdown(wait=False)
        _io_executor = None


async def run_db(fn: Callable[..., T], *args: Any, session_factory: Any = None) -> T:
    """Run a synchronous database/repository function on the db_executor with its own Session.

    Prevents blocking the FastAPI async event loop (Finding H11).
    """
    factory = session_factory or SessionLocal
    loop = asyncio.get_running_loop()

    def _worker() -> T:
        session = factory()
        try:
            return fn(session, *args)
        finally:
            session.close()

    return await loop.run_in_executor(get_db_executor(), _worker)
