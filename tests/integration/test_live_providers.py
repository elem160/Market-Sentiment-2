from datetime import timedelta

import pytest

from app.core.constants import FUTURE_CLOCK_SKEW_MINUTES
from app.core.enums import AssetType
from app.core.session_window import compute_session_window
from app.services.deduplication_service import DeduplicationService
from app.services.news_service import NewsService


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ticker, company_name, asset_type, yf_symbol",
    [
        ("AAPL", "Apple Inc.", AssetType.EQUITY, "AAPL"),
        ("BTC-USD", "Bitcoin USD", AssetType.CRYPTO, "BTC-USD"),
        ("EUR/USD", "Euro / US Dollar", AssetType.FOREX, "EURUSD=X"),
    ],
)
async def test_live_providers_return_titled_in_window_articles(ticker, company_name, asset_type, yf_symbol):
    """Live network test querying the real Yahoo Finance and Google News endpoints."""
    session = compute_session_window()
    articles, outcomes = await NewsService.fetch_news_for_session(
        ticker=ticker,
        company_name=company_name,
        session=session,
        asset_type=asset_type,
        yf_symbol=yf_symbol,
    )

    successful = [key for key, outcome in outcomes.items() if outcome.get("status") == "SUCCESS"]
    assert successful, f"No provider succeeded for {ticker}: {outcomes}"
    assert articles, f"No articles ingested for {ticker}"
    assert all(article.title.strip() for article in articles)

    in_window, _, _, _ = DeduplicationService.filter_by_session_window(articles, session)
    latest_allowed = session.window_end_utc + timedelta(minutes=FUTURE_CLOCK_SKEW_MINUTES)
    for article in in_window:
        assert article.published_at_utc is not None
        assert article.published_at_utc.tzinfo is not None
        assert session.window_start_utc <= article.published_at_utc <= latest_allowed
