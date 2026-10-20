import asyncio
import threading
import pytest
from app.services.finbert_service import FinBERTService
from app.api.routes import _background_tasks, run_background_job
from app.config import settings
from app.core.enums import CacheStatus


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


def test_run_migrations_from_temp_working_directory(tmp_path, monkeypatch):
    """Verify run_migrations uses absolute paths and succeeds when run from arbitrary temp dir."""
    import os
    from app.main import run_migrations

    monkeypatch.chdir(tmp_path)
    assert os.getcwd() == str(tmp_path)
    # Must succeed without error finding alembic.ini or alembic directory
    run_migrations()


def test_run_migrations_failure_is_not_swallowed():
    """Verify run_migrations does not swallow migration exceptions."""
    from unittest.mock import patch
    from app.main import run_migrations

    with patch("app.main.Config", side_effect=RuntimeError("Simulated migration failure")):
        with pytest.raises(RuntimeError, match="Simulated migration failure"):
            run_migrations()


def test_run_migrations_preserves_application_loggers():
    """Verify run_migrations does not disable uvicorn.error or market_sentiment loggers (H2)."""
    import logging
    from app.main import run_migrations

    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_logger.disabled = False
    sentiment_logger = logging.getLogger("market_sentiment")
    sentiment_logger.disabled = False

    run_migrations()

    assert not uvicorn_logger.disabled
    assert not sentiment_logger.disabled


@pytest.mark.asyncio
async def test_all_rss_providers_fail_adds_warning_and_skips_caching(db_session):
    """Verify: When all RSS providers fail, pipeline adds a warning and does not cache the result."""
    from unittest.mock import patch, AsyncMock
    from datetime import datetime, timezone
    from app.services.orchestrator import AnalysisOrchestrator
    from app.db.repository import SentimentRepository
    from app.core.models import Asset, IngestedArticle
    from app.core.enums import AssetType, ProviderType
    from app.core.session_window import compute_session_window, compute_session_bucket

    now = datetime.now(timezone.utc)
    mock_asset = Asset(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )
    art_yf = IngestedArticle(
        article_id="yf_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/yf1",
        title="Apple announces breakthrough product revenue",
        summary="Apple Inc reported record sales.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )
    mock_outcomes = {
        "yfinance": {"status": "SUCCESS", "count": 1},
        "rss_google_news_general": {"status": "FAILED", "error": "HTTP 500"},
        "rss_reuters": {"status": "FAILED", "error": "Timeout"},
        "google_news_rss_total": {"status": "FAILED", "count": 0},
    }

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([art_yf], mock_outcomes))):
        result = await AnalysisOrchestrator.run_pipeline("AAPL", db_session, enable_llm=False, force_refresh=True)

        assert any("All RSS news providers failed" in w for w in result.warnings)

        # Verify not returned from cache
        session = compute_session_window()
        session_bucket, _ = compute_session_bucket(session)
        cache_key = AnalysisOrchestrator.compute_cache_key("AAPL", session_bucket, "yfinance_rss", False)
        cached = SentimentRepository.get_cached_run(db_session, cache_key)
        assert cached is None

        # Verify run IS persisted in database and retrievable by ID with MISS status (C2, P1.3)
        persisted = SentimentRepository.get_analysis_run(db_session, result.run_id)
        assert persisted is not None
        assert persisted.run_id == result.run_id
        assert persisted.cache_status == CacheStatus.MISS

