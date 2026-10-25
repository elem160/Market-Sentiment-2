"""
Asset registry containing canonical alias dictionaries, common-word tickers,
currency definitions, futures keywords, crypto names, and search query helpers.
"""
import re
from dataclasses import dataclass

from app.core.enums import AssetType


@dataclass(frozen=True)
class EquityAlias:
    aliases: tuple[str, ...]
    ambiguous: bool = False


# Large caps, popular ETFs, and tickers prone to ambiguity
EQUITY_ALIASES: dict[str, EquityAlias] = {
    "GOOGL": EquityAlias(("Google", "Alphabet")),
    "GOOG": EquityAlias(("Google", "Alphabet")),
    "META": EquityAlias(("Meta Platforms", "Facebook")),
    "BRK-B": EquityAlias(("Berkshire Hathaway", "Berkshire")),
    "BRK.B": EquityAlias(("Berkshire Hathaway", "Berkshire")),
    "BRK-A": EquityAlias(("Berkshire Hathaway", "Berkshire")),
    "BRK.A": EquityAlias(("Berkshire Hathaway", "Berkshire")),
    "AMD": EquityAlias(("Advanced Micro Devices",)),
    "T": EquityAlias(("AT&T", "SBC Communications")),
    "SPY": EquityAlias(("S&P 500 ETF", "SPDR S&P 500", "S&P 500")),
    "QQQ": EquityAlias(("Invesco QQQ", "Nasdaq 100 ETF", "Triple Q")),
    "IWM": EquityAlias(("Russell 2000 ETF", "iShares Russell 2000")),
    "DIA": EquityAlias(("SPDR Dow Jones", "Dow ETF")),
    "AAPL": EquityAlias(("Apple",)),
    "MSFT": EquityAlias(("Microsoft",)),
    "AMZN": EquityAlias(("Amazon",)),
    "NVDA": EquityAlias(("Nvidia",)),
    "TSLA": EquityAlias(("Tesla",)),
    "NFLX": EquityAlias(("Netflix",)),
    "JPM": EquityAlias(("JPMorgan", "JP Morgan", "Chase")),
    "BAC": EquityAlias(("Bank of America", "BofA")),
    "WFC": EquityAlias(("Wells Fargo",)),
    "C": EquityAlias(("Citigroup", "Citi")),
    "GS": EquityAlias(("Goldman Sachs", "Goldman")),
    "MS": EquityAlias(("Morgan Stanley",)),
    "V": EquityAlias(("Visa",), ambiguous=True),
    "MA": EquityAlias(("Mastercard",)),
    "WMT": EquityAlias(("Walmart",)),
    "TGT": EquityAlias(("Target",), ambiguous=True),
    "GPS": EquityAlias(("Gap",), ambiguous=True),
    "F": EquityAlias(("Ford",), ambiguous=True),
    "SHEL": EquityAlias(("Shell",), ambiguous=True),
    "GM": EquityAlias(("General Motors",)),
    "GE": EquityAlias(("General Electric",)),
    "DIS": EquityAlias(("Disney", "Walt Disney")),
    "XOM": EquityAlias(("Exxon", "ExxonMobil")),
    "CVX": EquityAlias(("Chevron",)),
    "KO": EquityAlias(("Coca-Cola", "Coke")),
    "PEP": EquityAlias(("Pepsi", "PepsiCo")),
    "COST": EquityAlias(("Costco",)),
    "HD": EquityAlias(("Home Depot",)),
    "PG": EquityAlias(("Procter & Gamble", "P&G")),
    "JNJ": EquityAlias(("Johnson & Johnson", "J&J")),
    "UNH": EquityAlias(("UnitedHealth", "UnitedHealth Group")),
    "LLY": EquityAlias(("Eli Lilly", "Lilly")),
    "PFE": EquityAlias(("Pfizer",)),
    "MRK": EquityAlias(("Merck",)),
    "ABBV": EquityAlias(("AbbVie",)),
    "CRM": EquityAlias(("Salesforce",)),
    "ORCL": EquityAlias(("Oracle",)),
    "INTC": EquityAlias(("Intel",)),
    "CSCO": EquityAlias(("Cisco",)),
    "IBM": EquityAlias(("IBM", "International Business Machines")),
    "BA": EquityAlias(("Boeing",)),
    "CAT": EquityAlias(("Caterpillar",)),
    "UBER": EquityAlias(("Uber",)),
    "ABNB": EquityAlias(("Airbnb",)),
    "COIN": EquityAlias(("Coinbase",)),
    "PLTR": EquityAlias(("Palantir",)),
    "BABA": EquityAlias(("Alibaba",)),
    "NOW": EquityAlias(("ServiceNow",)),
    "ALL": EquityAlias(("Allstate",)),
    "LOW": EquityAlias(("Lowe's", "Lowes")),
    "KEY": EquityAlias(("KeyCorp", "KeyBank")),
    "ARE": EquityAlias(("Alexandria Real Estate",)),
    "HAS": EquityAlias(("Hasbro",)),
}

COMMON_WORD_TICKERS: frozenset[str] = frozenset({
    "NOW", "ALL", "ARE", "HAS", "CAT", "KEY", "LOW", "ON", "IT", "AI",
    "BIG", "FUN", "CAR", "EAT", "GOOD", "WELL", "FAST", "MAIN", "PLAY",
    "OPEN", "REAL", "SAFE", "TRUE", "BEST", "LIFE", "WORK", "ONE",
    "CAN", "SEE", "SO", "AM", "BE", "DO", "GO", "HE", "ME", "MY", "NO",
    "UP", "US", "WE", "AT", "BY", "IF", "IN", "OF", "OR", "TO", "A", "I",
    "OUT", "MAN", "JOB", "RUN", "PAY", "NEW", "TOP", "HOT", "GET", "WIN",
    "DAY", "NET", "TWO", "SIX", "TEN", "GAS", "OIL", "WAR", "SEA", "SUN",
    "SKY", "AIR", "FLY", "BUY", "BOX", "BAG", "BAR", "BED", "BIT", "BUS",
    "CUP", "DOG", "EAR", "EGG", "EYE", "FAR", "FAT", "FEW", "FIT", "FOX",
    "GUN", "HAT", "HIT", "ICE", "INK", "JAR", "JOY", "LAW", "LEG", "LIP",
    "MAP", "MUD", "PAN", "PEN", "PET", "PIN", "POT", "RAT", "RED", "ROW",
    "SAD", "SET", "TAX", "TIE", "TIP", "TOE", "VAN", "WET", "CRY", "DRY",
    "FRY", "LAY", "MAY", "SAY", "TRY", "WAY",
})

CURRENCY_NAMES: dict[str, tuple[str, ...]] = {
    "EUR": ("euro", "euros"),
    "USD": ("dollar", "dollars", "greenback"),
    "JPY": ("yen",),
    "GBP": ("sterling", "pound", "pounds", "cable"),
    "CHF": ("franc", "francs", "swissie"),
    "AUD": ("australian dollar", "aussie"),
    "CAD": ("canadian dollar", "loonie"),
    "NZD": ("new zealand dollar", "kiwi"),
    "CNY": ("yuan", "renminbi"),
    "SEK": ("krona", "kronor"),
    "NOK": ("krone", "kroner"),
}

FUTURES_KEYWORDS: dict[str, tuple[str, ...]] = {
    "GC=F": ("gold", "bullion"),
    "SI=F": ("silver",),
    "CL=F": ("crude", "oil", "wti", "opec"),
    "BZ=F": ("brent",),
    "NG=F": ("natural gas", "henry hub"),
    "HG=F": ("copper",),
    "ZW=F": ("wheat",),
    "ZC=F": ("corn",),
    "ZS=F": ("soybean", "soybeans"),
    "ES=F": ("s&p 500", "spx", "e-mini"),
    "NQ=F": ("nasdaq 100", "ndx"),
    "YM=F": ("dow", "dow jones"),
    "RTY=F": ("russell 2000",),
}

CRYPTO_NAMES: dict[str, tuple[str, ...]] = {
    "BTC": ("bitcoin",),
    "ETH": ("ethereum", "ether"),
    "SOL": ("solana",),
    "XRP": ("ripple",),
    "DOGE": ("dogecoin",),
    "ADA": ("cardano",),
    "BNB": ("binance coin", "bnb"),
}

MARKET_CONTEXT_TERMS: frozenset[str] = frozenset({
    "shares", "stock", "stocks", "earnings", "revenue", "sales", "guidance",
    "ceo", "retailer", "retailers", "inc", "corp", "corporation", "quarterly",
    "quarter", "profit", "profits", "dividend", "dividends", "investor", "investors",
    "analyst", "analysts", "market", "valuation",
})

GENERIC_NAME_TOKENS: frozenset[str] = frozenset({
    "micro", "general", "advanced", "united", "american", "national",
    "global", "digital", "energy", "capital", "financial", "motors",
    "international", "holdings", "group", "corp", "corporation",
    "inc", "incorporated", "ltd", "limited", "company", "co",
})

LEGAL_CORPORATE_SUFFIXES: frozenset[str] = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "llc", "plc", "sa", "ag", "nv", "spa", "holdings", "group",
})


def build_google_query_subject(ticker: str, company_name: str, asset_type: AssetType) -> str:
    """
    Builds Google RSS query subject based on the asset registry rules (M15):
    - Equities: ("Clean Name" OR TICKER)
    - Forex: ("EUR/USD" OR EURUSD)
    - Futures: ("crude oil" OR WTI), ("gold" OR bullion), etc.
    - Crypto: (Bitcoin OR BTC)
    """
    ticker_clean = ticker.strip()

    if asset_type == AssetType.FOREX:
        clean_fx = ticker_clean.replace("=X", "").replace("=x", "")
        if "/" in clean_fx:
            no_slash = clean_fx.replace("/", "")
            return f'("{clean_fx}" OR {no_slash})'
        elif len(clean_fx) == 6:
            pair_slash = f"{clean_fx[:3]}/{clean_fx[3:]}"
            return f'("{pair_slash}" OR {clean_fx})'
        return clean_fx

    if asset_type in (AssetType.COMMODITY, AssetType.FUTURES):
        norm_sym = ticker_clean.upper()
        if norm_sym == "CL=F":
            return '("crude oil" OR WTI)'
        if norm_sym == "GC=F":
            return '("gold" OR bullion)'
        if norm_sym == "ES=F":
            return '("S&P 500" OR SPX)'
        if norm_sym in FUTURES_KEYWORDS:
            kw = FUTURES_KEYWORDS[norm_sym]
            return f'("{kw[0]}" OR {kw[1]})' if len(kw) > 1 else f'"{kw[0]}"'
        return f'"{company_name}"' if company_name else ticker_clean

    if asset_type == AssetType.CRYPTO:
        crypto_sym = ticker_clean.split("-")[0].upper()
        if crypto_sym in CRYPTO_NAMES:
            name = CRYPTO_NAMES[crypto_sym][0].capitalize()
            return f'({name} OR {crypto_sym})'
        return f'({company_name} OR {crypto_sym})' if company_name else crypto_sym

    # Default Equity / ETF
    name_tokens = [
        w for w in re.findall(r"[a-zA-Z0-9]+", company_name)
        if w.lower() not in LEGAL_CORPORATE_SUFFIXES
    ]
    clean_name = " ".join(name_tokens).strip()
    if clean_name and clean_name.upper() != ticker_clean.upper():
        return f'("{clean_name}" OR {ticker_clean})'
    return ticker_clean
