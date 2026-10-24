import pytest
from unittest.mock import patch
from app.services.orchestrator import AnalysisOrchestrator
from app.core.models import Asset
from app.core.enums import AssetType, CacheStatus
from app.services.job_manager import JobManager


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
async def test_job_manager_request_coalescing():
    """Verify that concurrent requests for the same cache key coalesce onto the same job_id."""
    jm = JobManager()
    cache_key = "test_coalesce_key_123"

    with patch.object(jm, "_run_job"):
        job1_id, coalesced1, _ = await jm.submit("AAPL", cache_key=cache_key)
        assert coalesced1 is False

        job2_id, coalesced2, _ = await jm.submit("AAPL", cache_key=cache_key)
        assert coalesced2 is True
        assert job2_id == job1_id

        job_diff_id, coalesced_diff, _ = await jm.submit("MSFT", cache_key="other_cache_key")
        assert coalesced_diff is False
        assert job_diff_id != job1_id

    await jm.shutdown()
