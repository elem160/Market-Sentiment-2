import asyncio
import threading
import time
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.utils.executors import get_db_executor, get_io_executor, run_db, shutdown_executors


@pytest.mark.asyncio
async def test_run_db_executes_on_worker_thread():
    """Verify run_db executes on a worker thread in db_executor, not on the event loop thread."""
    main_thread = threading.current_thread()

    def get_worker_thread(db):
        return threading.current_thread()

    worker_thread = await run_db(get_worker_thread)
    assert worker_thread != main_thread
    assert "db_pool" in worker_thread.name


@pytest.mark.asyncio
async def test_health_check_responds_under_200ms_during_slow_db_write(async_client: AsyncClient):
    """Verify Finding H11: /health answers in < 200 ms while a slow DB operation runs on db_executor."""
    slow_done = False

    def slow_db_write(db):
        nonlocal slow_done
        # Run a write transaction with simulated duration
        db.execute(text("CREATE TEMPORARY TABLE IF NOT EXISTS test_slow_lock (id INT)"))
        db.execute(text("INSERT INTO test_slow_lock VALUES (1)"))
        time.sleep(0.5)  # 500 ms slow work on db_executor
        db.commit()
        slow_done = True
        return True

    # Launch slow DB task on db_executor
    slow_task = asyncio.create_task(run_db(slow_db_write))

    # Give the task a tiny moment to begin executing on db_executor
    await asyncio.sleep(0.02)

    # Concurrently request /health while slow_task is executing
    t0 = time.perf_counter()
    res = await async_client.get("/api/v1/health")
    latency_ms = (time.perf_counter() - t0) * 1000.0

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UP"
    assert data["database_status"] == "HEALTHY"

    # Must answer well under 200 ms (Finding H11 acceptance requirement)
    assert latency_ms < 200.0, f"Health check took {latency_ms:.1f}ms, expected < 200ms"

    # Wait for the slow task to cleanly complete
    await slow_task
    assert slow_done is True


def test_executors_creation_and_shutdown():
    """Verify executor instances are created on demand and cleanly shut down."""
    db_ex = get_db_executor()
    io_ex = get_io_executor()

    assert db_ex is not None
    assert io_ex is not None

    shutdown_executors()

    # Re-instantiation creates fresh pool
    db_ex2 = get_db_executor()
    assert db_ex2 is not None
    assert db_ex2 is not db_ex
    shutdown_executors()
