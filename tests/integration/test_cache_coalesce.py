import pytest
from unittest.mock import patch
from app.services.orchestrator import AnalysisOrchestrator
from app.core.models import Asset
from app.core.enums import AssetType, CacheStatus
from app.utils.lock_manager import TickerLockManager


@pytest.mark.asyncio
async def test_cache_hit_and_force_refresh(db_session, sample_aapl_articles):
    mock_asset = Asset(
        ticker="AAPL",
        company_name="Apple Inc.",
        exchange="NASDAQ",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
    )

    with patch("app.services.ticker_service.TickerService.validate_and_resolve", return_value=mock_asset), \
         patch("app.services.news_service.NewsService.fetch_news_for_session", return_value=(sample_aapl_articles, {"yfinance": {"status": "SUCCESS"}})):

        # 1. First Run -> Cache MISS
        run1 = await AnalysisOrchestrator.run_pipeline("AAPL", db_session, force_refresh=True, enable_llm=False)
        assert run1.cache_status == CacheStatus.MISS
        run1_id = run1.run_id

        # 2. Second Run without force_refresh -> Cache HIT
        run2 = await AnalysisOrchestrator.run_pipeline("AAPL", db_session, force_refresh=False, enable_llm=False)
        assert run2.cache_status == CacheStatus.HIT
        assert run2.run_id == run1_id

        # 3. Third Run with force_refresh=True -> Cache MISS (new run)
        run3 = await AnalysisOrchestrator.run_pipeline("AAPL", db_session, force_refresh=True, enable_llm=False)
        assert run3.cache_status == CacheStatus.MISS
        assert run3.run_id != run1_id


@pytest.mark.asyncio
async def test_ticker_lock_manager_coalescing():
    """Verify that lock manager normalizes ticker keys and provides shared mutex."""
    lock1 = await TickerLockManager.get_lock("AAPL")
    lock2 = await TickerLockManager.get_lock("aapl")
    lock3 = await TickerLockManager.get_lock("  AAPL  ")

    assert lock1 is lock2
    assert lock2 is lock3

    lock_diff = await TickerLockManager.get_lock("MSFT")
    assert lock1 is not lock_diff
