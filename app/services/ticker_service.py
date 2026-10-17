import re
import yfinance as yf
from app.core.models import Asset
from app.core.enums import AssetType
from app.core.exceptions import (
    InvalidTickerException,
    TickerNotFoundException,
)
from app.utils.logging import logger

FOREX_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "NZD", "CNY", "HKD", "SGD", "ZAR", "MXN", "SEK", "NOK"
}

COMMODITY_ALIASES = {
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "CRUDE": "CL=F",
    "OIL": "CL=F",
    "CRUDE OIL": "CL=F",
    "BRENT": "BZ=F",
    "NATURAL GAS": "NG=F",
    "COPPER": "HG=F",
    "WHEAT": "ZW=F",
    "CORN": "ZC=F",
    "SOYBEANS": "ZS=F",
    "SP500": "ES=F",
    "NASDAQ": "NQ=F",
}

CRYPTO_ALIASES = {
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD",
    "SOLANA": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
}

KNOWN_DISPLAY_NAMES = {
    "EUR/USD": "Euro / US Dollar",
    "EURUSD=X": "Euro / US Dollar",
    "USD/JPY": "US Dollar / Japanese Yen",
    "USDJPY=X": "US Dollar / Japanese Yen",
    "GBP/USD": "British Pound / US Dollar",
    "GBPUSD=X": "British Pound / US Dollar",
    "AUD/USD": "Australian Dollar / US Dollar",
    "AUDUSD=X": "Australian Dollar / US Dollar",
    "USD/CAD": "US Dollar / Canadian Dollar",
    "USDCAD=X": "US Dollar / Canadian Dollar",
    "USD/CHF": "US Dollar / Swiss Franc",
    "USDCHF=X": "US Dollar / Swiss Franc",
    "NZD/USD": "New Zealand Dollar / US Dollar",
    "NZDUSD=X": "New Zealand Dollar / US Dollar",
    "EUR/GBP": "Euro / British Pound",
    "EURGBP=X": "Euro / British Pound",
    "EUR/JPY": "Euro / Japanese Yen",
    "EURJPY=X": "Euro / Japanese Yen",
    "GC=F": "Gold Futures",
    "CL=F": "Crude Oil Futures",
    "SI=F": "Silver Futures",
    "NG=F": "Natural Gas Futures",
    "HG=F": "Copper Futures",
    "ES=F": "E-mini S&P 500 Futures",
    "NQ=F": "E-mini Nasdaq 100 Futures",
    "BTC-USD": "Bitcoin USD",
    "ETH-USD": "Ethereum USD",
    "SOL-USD": "Solana USD",
    "XRP-USD": "XRP USD",
    "DOGE-USD": "Dogecoin USD",
}


class TickerService:
    @staticmethod
    def normalize_ticker(raw_ticker: str) -> str:
        """Strip whitespace, leading $, and uppercase with syntax validation."""
        if not raw_ticker or not raw_ticker.strip():
            raise InvalidTickerException("", "Ticker cannot be empty")
        cleaned = raw_ticker.strip().upper()
        if cleaned.startswith("$"):
            cleaned = cleaned[1:]

        # Validate allowed characters: letters, digits, slash, dash, equals, dot
        if not re.match(r"^[A-Z0-9/=\.-]+$", cleaned):
            raise InvalidTickerException(raw_ticker, "Ticker contains invalid characters")

        # Normalize BRK.B to BRK-B (unless it's a forex pair with /)
        if "/" not in cleaned and "." in cleaned and not cleaned.endswith(".F"):
            cleaned = cleaned.replace(".", "-")

        # Length validation: if standard equity (no slash, no =, no -USD, not alias), limit to 6 chars
        if "/" not in cleaned and "=" not in cleaned and not cleaned.endswith("-USD"):
            if cleaned not in COMMODITY_ALIASES and cleaned not in CRYPTO_ALIASES and len(cleaned) > 6:
                raise InvalidTickerException(raw_ticker, "Equity tickers must be 1-6 characters")

        return cleaned

    @classmethod
    def format_yf_ticker(cls, raw: str) -> tuple[str, str, AssetType]:
        """
        Determines the display ticker, yfinance symbol, and AssetType.
        Returns: (display_ticker, yf_symbol, asset_type)
        """
        cleaned = cls.normalize_ticker(raw)

        # 1. Commodity Aliases
        if cleaned in COMMODITY_ALIASES:
            yf_sym = COMMODITY_ALIASES[cleaned]
            return yf_sym, yf_sym, AssetType.COMMODITY

        # 2. Crypto Aliases
        if cleaned in CRYPTO_ALIASES:
            yf_sym = CRYPTO_ALIASES[cleaned]
            return yf_sym, yf_sym, AssetType.CRYPTO

        # 3. Forex with slash notation (e.g. EUR/USD)
        if "/" in cleaned:
            parts = [p.strip() for p in cleaned.split("/") if p.strip()]
            if len(parts) == 2 and len(parts[0]) == 3 and len(parts[1]) == 3:
                yf_sym = f"{parts[0]}{parts[1]}=X"
                display = f"{parts[0]}/{parts[1]}"
                return display, yf_sym, AssetType.FOREX

        # 4. Forex with Yahoo =X notation (e.g. EURUSD=X)
        if cleaned.endswith("=X"):
            pair = cleaned[:-2]
            if len(pair) == 6:
                display = f"{pair[:3]}/{pair[3:]}"
            else:
                display = cleaned
            return display, cleaned, AssetType.FOREX

        # 5. Forex plain 6-letter (e.g. EURUSD)
        if len(cleaned) == 6 and cleaned[:3] in FOREX_CURRENCIES and cleaned[3:] in FOREX_CURRENCIES:
            yf_sym = f"{cleaned}=X"
            display = f"{cleaned[:3]}/{cleaned[3:]}"
            return display, yf_sym, AssetType.FOREX

        # 6. Commodities / Futures (e.g. GC=F, CL=F, ES=F)
        if cleaned.endswith("=F"):
            return cleaned, cleaned, AssetType.COMMODITY

        # 7. Crypto with -USD (e.g. BTC-USD)
        if cleaned.endswith("-USD") or "-EUR" in cleaned:
            return cleaned, cleaned, AssetType.CRYPTO

        # 8. Single standalone currency code (e.g. EUR -> EUR/USD default)
        if cleaned in FOREX_CURRENCIES:
            if cleaned != "USD":
                display = f"{cleaned}/USD"
                yf_sym = f"{cleaned}USD=X"
            else:
                display = "EUR/USD"
                yf_sym = "EURUSD=X"
            return display, yf_sym, AssetType.FOREX

        # 9. Standard Equities and ETFs (e.g. AAPL, NVDA, SPY, QQQ, BRK-B)
        return cleaned, cleaned, AssetType.EQUITY

    @classmethod
    def validate_and_resolve(cls, raw_ticker: str) -> Asset:
        """
        Universal asset resolution for Equities, ETFs, Forex, Commodities, and Crypto.
        """
        display_ticker, yf_symbol, detected_type = cls.format_yf_ticker(raw_ticker)

        # Check known display names first
        company_name = KNOWN_DISPLAY_NAMES.get(display_ticker) or KNOWN_DISPLAY_NAMES.get(yf_symbol)
        exchange = "US" if detected_type in (AssetType.EQUITY, AssetType.ETF) else ("CCY" if detected_type == AssetType.FOREX else "CME")
        sector = "Financials" if detected_type == AssetType.FOREX else ("Commodities" if detected_type == AssetType.COMMODITY else "")
        asset_type = detected_type

        # Query yfinance for additional profile data if not fully resolved
        try:
            ticker_obj = yf.Ticker(yf_symbol)
            fast_info = getattr(ticker_obj, "fast_info", None)

            if fast_info is not None:
                try:
                    q = getattr(fast_info, "quote_type", None) or getattr(fast_info, "quoteType", None)
                    if isinstance(q, str):
                        quote_str = q.upper()
                        if "ETF" in quote_str:
                            asset_type = AssetType.ETF
                        elif "EQUITY" in quote_str:
                            asset_type = AssetType.EQUITY
                        elif "CRYPTOCURRENCY" in quote_str or "CRYPTO" in quote_str:
                            asset_type = AssetType.CRYPTO
                        elif "CURRENCY" in quote_str or "FOREX" in quote_str:
                            asset_type = AssetType.FOREX
                        elif "COMMODITY" in quote_str or "FUTURE" in quote_str:
                            asset_type = AssetType.COMMODITY

                    ex = getattr(fast_info, "exchange", None)
                    if isinstance(ex, str) and ex:
                        exchange = ex

                    nm = getattr(fast_info, "long_name", None) or getattr(fast_info, "short_name", None)
                    if isinstance(nm, str) and nm and not company_name:
                        company_name = nm
                except Exception as ex:
                    logger.debug(f"Could not read fast_info for {yf_symbol}: {ex}")

            # Fallback to info dict if name still needed
            if not company_name:
                try:
                    info = getattr(ticker_obj, "info", None)
                    if isinstance(info, dict) and info:
                        q = info.get("quoteType", "")
                        if "ETF" in q.upper():
                            asset_type = AssetType.ETF
                        company_name = info.get("longName") or info.get("shortName")
                        exchange = info.get("exchange") or exchange
                        sector = info.get("sector") or sector
                except Exception as ex:
                    logger.debug(f"Could not read info for {yf_symbol}: {ex}")

        except Exception as e:
            logger.warning(f"Error querying yfinance for {yf_symbol}: {e}")

        if not company_name:
            company_name = display_ticker

        return Asset(
            ticker=display_ticker,
            company_name=company_name,
            exchange=exchange,
            sector=sector,
            asset_type=asset_type,
            is_active=True,
            yf_symbol=yf_symbol,
        )
