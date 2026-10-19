import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from app.services.ticker_service import TickerService
from app.core.exceptions import (
    InvalidTickerException,
    UnsupportedAssetException,
    TickerNotFoundException,
)
from app.core.enums import AssetType


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


def test_multi_asset_resolution():
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


@pytest.fixture(autouse=True)
def clear_ticker_cache():
    TickerService.clear_cache()
    yield
    TickerService.clear_cache()


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


def test_dollar_prefix_bypasses_commodity_aliases():
    """Verify F-18: $ prefix bypasses commodity/crypto aliases, resolving as equity."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "EQUITY"
        mock_instance.fast_info.long_name = "Barrick Gold Corporation"
        mock_instance.fast_info.exchange = "NYQ"
        mock_yf.return_value = mock_instance

        # Unprefixed GOLD resolves to commodity futures
        gold_commodity = TickerService.validate_and_resolve("GOLD")
        assert gold_commodity.ticker == "GC=F"
        assert gold_commodity.asset_type == AssetType.COMMODITY

        # Prefixed $GOLD resolves as listed equity
        gold_equity = TickerService.validate_and_resolve("$GOLD")
        assert gold_equity.ticker == "GOLD"
        assert gold_equity.yf_symbol == "GOLD"
        assert gold_equity.asset_type == AssetType.EQUITY


def test_ticker_resolution_caching():
    """Verify resolution is cached in-memory and avoids repeated external queries."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        mock_instance.fast_info.quote_type = "EQUITY"
        mock_instance.fast_info.long_name = "Microsoft Corporation"
        mock_instance.fast_info.exchange = "NMS"
        mock_yf.return_value = mock_instance

        # First call hits mock_yf
        asset1 = TickerService.validate_and_resolve("MSFT")
        assert mock_yf.call_count == 1

        # Second call hits resolution cache
        asset2 = TickerService.validate_and_resolve("MSFT")
        assert mock_yf.call_count == 1  # No additional network call
        assert asset1.ticker == asset2.ticker
        assert asset1.company_name == asset2.company_name


def test_missing_instrument_raises_404_not_found():
    """Verify F-18: When Yahoo explicitly reports 404 / Not Found and symbol is not known, raise 404."""
    with patch("yfinance.Ticker") as mock_yf:
        mock_instance = MagicMock()
        type(mock_instance).fast_info = PropertyMock(side_effect=Exception("404 Client Error: Not Found for url"))
        type(mock_instance).info = PropertyMock(side_effect=Exception("404 Client Error: Not Found"))
        mock_yf.return_value = mock_instance

        with pytest.raises(TickerNotFoundException) as exc_info:
            TickerService.validate_and_resolve("NOTFND")
        assert exc_info.value.status_code == 404


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

