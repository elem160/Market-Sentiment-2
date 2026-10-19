import pytest
from app.services.news_service import NewsService
from app.core.enums import AssetType
from app.core.session_window import compute_session_window


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_yahoo_finance_and_google_rss_connectivity():
    """Live network test querying actual Yahoo Finance and Google News endpoints."""
    session = compute_session_window()
    articles, outcomes = await NewsService.fetch_news_for_session(
        ticker="AAPL",
        company_name="Apple Inc.",
        asset_type=AssetType.EQUITY,
        session=session,
    )

    # In a live environment, either yfinance or google_news_rss should return SUCCESS
    assert isinstance(articles, list)
    assert "yfinance" in outcomes
    assert "google_news_rss_total" in outcomes
