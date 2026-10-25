from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import time_machine

from app.core.enums import AssetType
from app.core.exceptions import (
    InvalidTickerException,
    ProviderException,
    TickerNotFoundException,
)
from app.core.models import Asset
from app.services.orchestrator import AnalysisOrchestrator
from app.services.ticker_service import TickerService


@pytest.fixture(autouse=True)
def clear_ticker_cache():
    TickerService.clear_cache()
    yield
    TickerService.clear_cache()


def test_normalize_ticker():
    assert TickerService.normalize_ticker("aapl") == "AAPL"
    assert TickerService.normalize_ticker("  $msft  ") == "MSFT"
    assert TickerService.normalize_ticker("brk.b") == "BRK-B"
    assert TickerService.normalize_ticker("BRK-B") == "BRK-B"


def test_invalid_syntax_rejection():
    with pytest.raises(InvalidTickerException):
        TickerService.normalize_ticker("")

    with pytest.raises(InvalidTickerException):
        TickerService.validate_and_resolve("TOOLONGTICKER")

    with pytest.raises(InvalidTickerException):
        TickerService.validate_and_resolve("NV_DA")


@pytest.fixture
def yahoo_without_profile_data():
    """Yahoo stub that answers but exposes no profile fields (no hidden network calls)."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_yf.return_value = MagicMock(
            fast_info=SimpleNamespace(quote_type=None, exchange=None, long_name=None, short_name=None),
            info={},
        )
        yield mock_yf


def test_multi_asset_resolution(yahoo_without_profile_data):
    # Forex
    fx1 = TickerService.validate_and_resolve("EUR/USD")
    assert fx1.ticker == "EUR/USD"
    assert fx1.yf_symbol == "EURUSD=X"
    assert fx1.asset_type == AssetType.FOREX

    fx2 = TickerService.validate_and_resolve("USD/JPY")
    assert fx2.ticker == "USD/JPY"
    assert fx2.yf_symbol == "USDJPY=X"
    assert fx2.asset_type == AssetType.FOREX

    # Commodities & Aliases
    gold = TickerService.validate_and_resolve("GOLD")
    assert gold.ticker == "GC=F"
    assert gold.yf_symbol == "GC=F"
    assert gold.asset_type == AssetType.COMMODITY

    oil = TickerService.validate_and_resolve("CL=F")
    assert oil.ticker == "CL=F"
    assert oil.asset_type == AssetType.COMMODITY

    # Crypto & Aliases
    btc = TickerService.validate_and_resolve("BTC")
    assert btc.ticker == "BTC-USD"
    assert btc.asset_type == AssetType.CRYPTO

    eth = TickerService.validate_and_resolve("ETH-USD")
    assert eth.ticker == "ETH-USD"
    assert eth.asset_type == AssetType.CRYPTO

    # Every resolution went through the explicit Yahoo stub
    assert {c.args[0] for c in yahoo_without_profile_data.call_args_list} == {
        "EURUSD=X", "USDJPY=X", "GC=F", "CL=F", "BTC-USD", "ETH-USD"
    }


def test_successful_ticker_resolution():
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "EQUITY"
        mock_instance.fast_info.long_name = "Apple Inc."
        mock_instance.fast_info.exchange = "NMS"
        mock_yf.return_value = mock_instance

        asset = TickerService.validate_and_resolve("AAPL")
        assert asset.ticker == "AAPL"
        assert asset.company_name == "Apple Inc."
        assert asset.asset_type == AssetType.EQUITY
        assert asset.is_active is True
        assert asset.verified is True
        assert asset.resolution_warning is None


def test_successful_etf_resolution():
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "ETF"
        mock_instance.fast_info.long_name = "SPDR S&P 500 ETF Trust"
        mock_instance.fast_info.exchange = "PCX"
        mock_yf.return_value = mock_instance

        asset = TickerService.validate_and_resolve("SPY")
        assert asset.ticker == "SPY"
        assert asset.asset_type == AssetType.ETF


def test_gold_cross_mode_isolation():
    """Verify H5: Resolving GOLD -> GC=F, then $GOLD -> GOLD (equity), then GOLD -> still GC=F."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "EQUITY"
        mock_instance.fast_info.long_name = "Barrick Gold Corporation"
        mock_instance.fast_info.exchange = "NYQ"
        mock_yf.return_value = mock_instance

        # 1. Unprefixed GOLD resolves to commodity futures
        gold_commodity = TickerService.validate_and_resolve("GOLD")
        assert gold_commodity.ticker == "GC=F"
        assert gold_commodity.asset_type == AssetType.COMMODITY

        # 2. Prefixed $GOLD resolves as listed equity
        gold_equity = TickerService.validate_and_resolve("$GOLD")
        assert gold_equity.ticker == "GOLD"
        assert gold_equity.yf_symbol == "GOLD"
        assert gold_equity.asset_type == AssetType.EQUITY
        assert gold_equity.company_name == "Barrick Gold Corporation"

        # 3. Subsequent call to GOLD is still GC=F (no cross-mode cache pollution)
        gold_commodity_again = TickerService.validate_and_resolve("GOLD")
        assert gold_commodity_again.ticker == "GC=F"
        assert gold_commodity_again.asset_type == AssetType.COMMODITY


def test_dollar_corn_bypass():
    """Verify $CORN bypasses corn futures alias (ZC=F) and resolves as equity/ETF."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "ETF"
        mock_instance.fast_info.long_name = "Teucrium Corn Fund"
        mock_instance.fast_info.exchange = "PCX"
        mock_yf.return_value = mock_instance

        # Unprefixed CORN resolves to commodity futures
        corn_fut = TickerService.validate_and_resolve("CORN")
        assert corn_fut.ticker == "ZC=F"
        assert corn_fut.asset_type == AssetType.COMMODITY

        # Prefixed $CORN resolves as listed ETF
        corn_etf = TickerService.validate_and_resolve("$CORN")
        assert corn_etf.ticker == "CORN"
        assert corn_etf.asset_type == AssetType.ETF
        assert corn_etf.company_name == "Teucrium Corn Fund"


def test_futures_asset_typing():
    """Verify ES=F, NQ=F, YM=F, RTY=F and aliases resolve as AssetType.FUTURES with CME exchange."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info = SimpleNamespace(quote_type=None, exchange=None, long_name=None, short_name=None)
        mock_instance.info = {}
        mock_yf.return_value = mock_instance

        for sym in ("ES=F", "NQ=F", "YM=F", "RTY=F"):
            res = TickerService.validate_and_resolve(sym)
            assert res.asset_type == AssetType.FUTURES
            assert res.exchange == "CME"

        sp500 = TickerService.validate_and_resolve("SP500")
        assert sp500.ticker == "ES=F"
        assert sp500.asset_type == AssetType.FUTURES

        nasdaq = TickerService.validate_and_resolve("NASDAQ")
        assert nasdaq.ticker == "NQ=F"
        assert nasdaq.asset_type == AssetType.FUTURES


def test_unknown_symbol_404_and_negative_cache():
    """Verify unknown symbol raises 404, enters negative cache, and expires after TTL."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info = SimpleNamespace(quote_type=None, exchange=None, long_name=None, short_name=None)
        mock_instance.info = {}
        mock_instance.history.return_value = MagicMock(empty=True)
        mock_yf.return_value = mock_instance

        # 1. First call fails with 404
        with pytest.raises(TickerNotFoundException) as exc_info:
            TickerService.validate_and_resolve("XYZABC")
        assert exc_info.value.status_code == 404
        assert "could not be resolved on Yahoo Finance" in exc_info.value.message
        assert mock_yf.call_count == 1

        # 2. Second call hits negative cache without calling yfinance
        with pytest.raises(TickerNotFoundException) as exc_info2:
            TickerService.validate_and_resolve("XYZABC")
        assert exc_info2.value.status_code == 404
        assert mock_yf.call_count == 1  # No additional call

        # 3. After negative TTL (600s), re-queries yfinance
        base_time = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
        with time_machine.travel(base_time + timedelta(seconds=605)):
            with pytest.raises(TickerNotFoundException):
                TickerService.validate_and_resolve("XYZABC")
            assert mock_yf.call_count == 2


def test_transport_error_resolves_unverified_with_warning():
    """Verify transport errors resolve as unverified (verified=False) with resolution_warning."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        type(mock_instance).fast_info = PropertyMock(side_effect=ConnectionError("Failed to establish a new connection"))
        type(mock_instance).info = PropertyMock(side_effect=ConnectionError("Connection aborted"))
        mock_yf.return_value = mock_instance

        asset = TickerService.validate_and_resolve("DISCON")
        assert asset.ticker == "DISCON"
        assert asset.verified is False
        assert asset.resolution_warning is not None
        assert "communication error" in asset.resolution_warning.lower() or "connection" in asset.resolution_warning.lower()


def test_throttled_or_empty_response_does_not_404():
    """Verify F-18: Throttled (429) or empty responses log warning and do NOT raise 404."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        type(mock_instance).fast_info = PropertyMock(side_effect=Exception("429 Client Error: Too Many Requests"))
        type(mock_instance).info = PropertyMock(side_effect=Exception("Rate limit exceeded"))
        mock_yf.return_value = mock_instance

        # Must not raise TickerNotFoundException; falls back with warning
        asset = TickerService.validate_and_resolve("THROTL")
        assert asset.ticker == "THROTL"
        assert asset.company_name == "THROTL"
        assert asset.verified is False
        assert asset.resolution_warning is not None


def test_ttl_cache_expiry():
    """Verify successful resolution cache expires after TICKER_CACHE_TTL_SECONDS (6h)."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "EQUITY"
        mock_instance.fast_info.long_name = "Apple Inc."
        mock_instance.fast_info.exchange = "NMS"
        mock_yf.return_value = mock_instance

        base_time = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
        with time_machine.travel(base_time, tick=False):
            asset1 = TickerService.validate_and_resolve("AAPL")
            assert mock_yf.call_count == 1

        # Within TTL (e.g. + 1 hour)
        with time_machine.travel(base_time + timedelta(hours=1), tick=False):
            asset2 = TickerService.validate_and_resolve("AAPL")
            assert mock_yf.call_count == 1
            assert asset2.ticker == asset1.ticker

        # Beyond TTL (6 hours + 10 seconds = 21610s)
        with time_machine.travel(base_time + timedelta(seconds=21610), tick=False):
            asset3 = TickerService.validate_and_resolve("AAPL")
            assert mock_yf.call_count == 2
            assert asset3.ticker == "AAPL"


@pytest.mark.asyncio
async def test_resolve_ticker_async_timeout():
    """Verify resolve_ticker_async raises ProviderException with status 503 on timeout."""
    def slow_resolve(ticker: str):
        import time
        time.sleep(0.5)

    with patch.object(TickerService, "validate_and_resolve", side_effect=slow_resolve), \
         patch("app.config.settings.TICKER_RESOLUTION_TIMEOUT_SECONDS", 0.05):
        with pytest.raises(ProviderException) as exc_info:
            await TickerService.resolve_ticker_async("SLOWTICKER")
        assert exc_info.value.status_code == 503
        assert "timed out" in exc_info.value.message


@pytest.mark.asyncio
async def test_orchestrator_never_calls_validate_and_resolve(db_session):
    """Verify the orchestrator uses passed asset directly and never re-resolves."""
    custom_asset = Asset(
        ticker="CUSTOM",
        company_name="Custom Unverified Corp",
        exchange="US",
        sector="Technology",
        asset_type=AssetType.EQUITY,
        is_active=True,
        yf_symbol="CUSTOM",
        verified=False,
        resolution_warning="Yahoo Finance communication error for CUSTOM: connection dropped",
    )

    from app.core.enums import ProviderType
    from app.core.models import IngestedArticle

    art_yf = IngestedArticle(
        article_id="custom_art_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/art1",
        title="Custom Corp launches breakthrough product",
        summary="Custom Corp details new product line.",
        published_at_utc=datetime.now(timezone.utc),
        retrieved_at_utc=datetime.now(timezone.utc),
        raw_provider_metadata={},
    )

    with patch.object(TickerService, "validate_and_resolve") as mock_resolve, \
         patch("app.services.news_service.NewsService.fetch_news_for_session", new=AsyncMock(return_value=([art_yf], {"yfinance": {"status": "SUCCESS", "count": 1}}))):
        result = await AnalysisOrchestrator.run_pipeline(
            "CUSTOM",
            db_session,
            force_refresh=True,
            enable_llm=False,
            asset=custom_asset,
        )

        # Orchestrator must NEVER have called validate_and_resolve
        mock_resolve.assert_not_called()

        assert result.ticker == "CUSTOM"
        assert result.company_name == "Custom Unverified Corp"
        # Warning from unverified asset must be preserved in result.warnings
        assert any("Yahoo Finance communication error" in w for w in result.warnings)
