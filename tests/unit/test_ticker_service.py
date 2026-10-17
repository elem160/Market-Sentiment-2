import pytest
from unittest.mock import patch, MagicMock
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

