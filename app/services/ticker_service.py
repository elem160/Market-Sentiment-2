import asyncio
import re
import time
import yfinance as yf
from app.config import settings
from app.core.models import Asset
from app.core.enums import AssetType
from app.core.exceptions import (
    InvalidTickerException,
    TickerNotFoundException,
    ProviderException,
)
from app.utils.logging import logger

FOREX_CURRENCIES = {
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "NZD", "CNY", "HKD", "SGD", "ZAR", "MXN", "SEK", "NOK"
}

FUTURES_TICKERS = {
    "ES=F", "NQ=F", "YM=F", "RTY=F"
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
    "YM=F": "E-mini Dow Futures",
    "RTY=F": "E-mini Russell 2000 Futures",
    "BTC-USD": "Bitcoin USD",
    "ETH-USD": "Ethereum USD",
    "SOL-USD": "Solana USD",
    "XRP-USD": "XRP USD",
    "DOGE-USD": "Dogecoin USD",
}

TRANSPORT_ERROR_KEYWORDS = (
    "connection", "timeout", "timed out", "unreachable", "name resolution",
    "dns", "proxy", "network", "socket", "reset by peer", "rate limit",
    "too many requests", "429", "500", "502", "503", "504", "service unavailable",
    "bad gateway", "gateway timeout"
)


def is_transport_error(exc: Exception) -> bool:
    exc_str = str(exc).lower()
    if "404" in exc_str or "not found" in exc_str or "delisted" in exc_str:
        return False
    if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
        return True
    return any(kw in exc_str for kw in TRANSPORT_ERROR_KEYWORDS)


class TickerService:
    # Key: (normalized_ticker, bypass_aliases) -> (timestamp, Asset)
    _resolution_cache: dict[tuple[str, bool], tuple[float, Asset]] = {}
    # Key: (normalized_ticker, bypass_aliases) -> (timestamp, reason)
    _negative_cache: dict[tuple[str, bool], tuple[float, str]] = {}

    @classmethod
    def clear_cache(cls):
        """Clear both resolution and negative in-memory caches."""
        cls._resolution_cache.clear()
        cls._negative_cache.clear()

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
    def parse_ticker_input(cls, raw_ticker: str) -> tuple[str, bool]:
        """Strip whitespace, check leading '$', and normalize syntax."""
        if not raw_ticker or not raw_ticker.strip():
            raise InvalidTickerException("", "Ticker cannot be empty")
        raw_stripped = raw_ticker.strip()
        bypass_aliases = raw_stripped.startswith("$")
        cleaned = cls.normalize_ticker(raw_stripped)
        return cleaned, bypass_aliases

    @classmethod
    def format_yf_ticker(cls, raw: str) -> tuple[str, str, AssetType]:
        """
        Determines the display ticker, yfinance symbol, and AssetType.
        If the ticker explicitly begins with '$', aliases (like GOLD -> GC=F) are bypassed
        so the symbol resolves directly as a listed equity.
        Returns: (display_ticker, yf_symbol, asset_type)
        """
        cleaned, bypass_aliases = cls.parse_ticker_input(raw)

        if not bypass_aliases:
            # 1. Commodity / Futures Aliases
            if cleaned in COMMODITY_ALIASES:
                yf_sym = COMMODITY_ALIASES[cleaned]
                asset_type = AssetType.FUTURES if yf_sym in FUTURES_TICKERS else AssetType.COMMODITY
                return yf_sym, yf_sym, asset_type

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

        # 6. Futures / Commodities (e.g. ES=F, GC=F)
        if cleaned in FUTURES_TICKERS:
            return cleaned, cleaned, AssetType.FUTURES
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

        # 9. Standard Equities and ETFs (e.g. AAPL, NVDA, SPY, QQQ, BRK-B, or $GOLD)
        return cleaned, cleaned, AssetType.EQUITY

    @classmethod
    def validate_and_resolve(cls, raw_ticker: str) -> Asset:
        """
        Universal asset resolution for Equities, ETFs, Forex, Commodities, Futures, and Crypto.
        Resolution results are cached in-memory per (normalized, bypass_aliases) tuple with TTL.
        Negative responses are cached for 10 minutes.
        """
        cleaned, bypass_aliases = cls.parse_ticker_input(raw_ticker)
        cache_key = (cleaned, bypass_aliases)
        now = time.time()

        # Check negative cache
        if cache_key in cls._negative_cache:
            neg_ts, neg_reason = cls._negative_cache[cache_key]
            if now - neg_ts < settings.TICKER_NEGATIVE_CACHE_TTL_SECONDS:
                raise TickerNotFoundException(raw_ticker, neg_reason)
            else:
                del cls._negative_cache[cache_key]

        # Check resolution cache
        if cache_key in cls._resolution_cache:
            res_ts, cached_asset = cls._resolution_cache[cache_key]
            if now - res_ts < settings.TICKER_CACHE_TTL_SECONDS:
                return cached_asset
            else:
                del cls._resolution_cache[cache_key]

        display_ticker, yf_symbol, detected_type = cls.format_yf_ticker(raw_ticker)

        is_known = (
            display_ticker in KNOWN_DISPLAY_NAMES
            or yf_symbol in KNOWN_DISPLAY_NAMES
            or detected_type in (AssetType.FOREX, AssetType.COMMODITY, AssetType.FUTURES, AssetType.CRYPTO)
        )
        company_name = KNOWN_DISPLAY_NAMES.get(display_ticker) or KNOWN_DISPLAY_NAMES.get(yf_symbol)

        default_exchange = (
            "CCC" if detected_type == AssetType.CRYPTO
            else ("CCY" if detected_type == AssetType.FOREX
            else ("CME" if detected_type in (AssetType.COMMODITY, AssetType.FUTURES)
            else "US"))
        )
        exchange = default_exchange
        sector = (
            "Financials" if detected_type == AssetType.FOREX
            else ("Index Futures" if detected_type == AssetType.FUTURES
            else ("Commodities" if detected_type == AssetType.COMMODITY
            else ("Cryptocurrency" if detected_type == AssetType.CRYPTO else "")))
        )
        asset_type = detected_type
        verified = True
        resolution_warning: str | None = None

        quote_type = None
        has_history = False
        transport_error = False
        transport_error_str = ""

        try:
            ticker_obj = yf.Ticker(yf_symbol)
            fast_info = getattr(ticker_obj, "fast_info", None)

            if fast_info is not None:
                try:
                    q = getattr(fast_info, "quote_type", None) or getattr(fast_info, "quoteType", None)
                    if isinstance(q, str) and q.strip():
                        quote_type = q.strip().upper()
                        if detected_type in (AssetType.EQUITY, AssetType.ETF):
                            if "ETF" in quote_type:
                                asset_type = AssetType.ETF
                            elif "EQUITY" in quote_type:
                                asset_type = AssetType.EQUITY

                    ex = getattr(fast_info, "exchange", None)
                    if isinstance(ex, str) and ex:
                        exchange = ex

                    nm = getattr(fast_info, "long_name", None) or getattr(fast_info, "short_name", None)
                    if isinstance(nm, str) and nm and not company_name:
                        company_name = nm
                except Exception as ex:
                    if is_transport_error(ex):
                        transport_error = True
                        transport_error_str = str(ex)
                    logger.debug(f"Could not read fast_info for {yf_symbol}: {ex}")

            # Fallback to info dict if name or quote_type still needed
            if not company_name or not quote_type:
                try:
                    info = getattr(ticker_obj, "info", None)
                    if isinstance(info, dict) and info:
                        q = info.get("quoteType", "")
                        if isinstance(q, str) and q.strip():
                            quote_type = quote_type or q.strip().upper()
                            if detected_type in (AssetType.EQUITY, AssetType.ETF):
                                if "ETF" in quote_type:
                                    asset_type = AssetType.ETF
                        company_name = company_name or info.get("longName") or info.get("shortName")
                        exchange = info.get("exchange") or exchange
                        sector = info.get("sector") or sector
                except Exception as ex:
                    if is_transport_error(ex):
                        transport_error = True
                        transport_error_str = str(ex)
                    logger.debug(f"Could not read info for {yf_symbol}: {ex}")

            # Check 5-day history if quote_type is not available
            if not quote_type:
                try:
                    hist_fn = getattr(ticker_obj, "history", None)
                    if callable(hist_fn):
                        hist = hist_fn(period="5d")
                        if hist is not None:
                            if hasattr(hist, "empty"):
                                has_history = not hist.empty
                            else:
                                has_history = len(hist) > 0
                except Exception as ex:
                    if is_transport_error(ex):
                        transport_error = True
                        transport_error_str = str(ex)
                    logger.debug(f"Could not read history for {yf_symbol}: {ex}")

        except Exception as e:
            if is_transport_error(e):
                transport_error = True
                transport_error_str = str(e)
            else:
                logger.warning(f"Error querying yfinance for {yf_symbol}: {e}")

        if transport_error:
            verified = False
            resolution_warning = f"Yahoo Finance communication error for {yf_symbol}: {transport_error_str}"
            logger.warning(resolution_warning)
        elif not is_known and not quote_type and not has_history:
            reason = "Symbol could not be resolved on Yahoo Finance."
            cls._negative_cache[cache_key] = (time.time(), reason)
            raise TickerNotFoundException(raw_ticker, reason)

        if not company_name:
            company_name = display_ticker

        asset = Asset(
            ticker=display_ticker,
            company_name=company_name,
            exchange=exchange,
            sector=sector,
            asset_type=asset_type,
            is_active=True,
            yf_symbol=yf_symbol,
            verified=verified,
            resolution_warning=resolution_warning,
        )

        cls._resolution_cache[cache_key] = (time.time(), asset)
        return asset

    @classmethod
    async def resolve_ticker_async(cls, raw_ticker: str) -> Asset:
        """
        Asynchronously resolves a ticker in a worker thread bounded by TICKER_RESOLUTION_TIMEOUT_SECONDS.
        Raises ProviderException with status 503 on timeout.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(cls.validate_and_resolve, raw_ticker),
                timeout=float(settings.TICKER_RESOLUTION_TIMEOUT_SECONDS),
            )
        except asyncio.TimeoutError:
            raise ProviderException(
                "Yahoo Finance",
                f"Ticker resolution timed out after {settings.TICKER_RESOLUTION_TIMEOUT_SECONDS}s",
                status_code=503,
            )
