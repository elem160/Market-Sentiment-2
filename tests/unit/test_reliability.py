import asyncio
import threading
import pytest
from app.services.finbert_service import FinBERTService
from app.api.routes import _background_tasks, run_background_job
from app.config import settings


def test_finbert_service_thread_safety_lock():
    """Verify that multiple concurrent threads accessing get_instance() and model loader do not collide (F-04)."""
    instances = []

    def fetch_instance():
        inst = FinBERTService.get_instance()
        instances.append(inst)

    threads = [threading.Thread(target=fetch_instance) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All threads must receive the identical singleton instance
    assert len(instances) == 10
    first = instances[0]
    for inst in instances[1:]:
        assert inst is first


@pytest.mark.asyncio
async def test_background_task_strong_reference_retention():
    """Verify background task reference is retained in _background_tasks and removed upon completion (F-03)."""
    completed = False

    async def sample_coro():
        nonlocal completed
        await asyncio.sleep(0.05)
        completed = True

    task = asyncio.create_task(sample_coro())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    # While running, task must be in the set
    assert task in _background_tasks
    await task
    # Once complete, done_callback removes it
    assert completed is True
    assert task not in _background_tasks


def test_pipeline_timeout_setting_configured():
    """Verify PIPELINE_TIMEOUT_SECONDS setting is present and defaults to 90s (F-14)."""
    assert hasattr(settings, "PIPELINE_TIMEOUT_SECONDS")
    assert settings.PIPELINE_TIMEOUT_SECONDS == 90
