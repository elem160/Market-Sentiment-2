"""
Deterministic multi-asset relevance engine (C3, H4, M15).
Evaluates headline and lead summary relevance across Equities, Forex, Futures/Commodities, and Crypto.
"""
import re
from typing import Literal

from app.core.asset_registry import (
    COMMON_WORD_TICKERS,
    CRYPTO_NAMES,
    CURRENCY_NAMES,
    EQUITY_ALIASES,
    FUTURES_KEYWORDS,
    GENERIC_NAME_TOKENS,
    LEGAL_CORPORATE_SUFFIXES,
    MARKET_CONTEXT_TERMS,
)
from app.core.enums import AssetType
from app.core.models import Asset

MatchReason = Literal[
    "CASHTAG",
    "EXCHANGE_TICKER",
    "TICKER",
    "ALIAS",
    "NAME",
    "PAIR",
    "CURRENCY_NAMES",
    "KEYWORD",
]

KNOWN_CURRENCIES = frozenset({
    "EUR", "USD", "JPY", "GBP", "CHF", "AUD", "CAD", "NZD", "CNY",
    "SEK", "NOK", "MXN", "SGD", "HKD",
})

NON_USD_DOLLAR_RE = re.compile(
    r"\b(?:australian|canadian|new zealand|hong kong|singapore|aussie)\s+dollars?\b",
    re.IGNORECASE,
)

EXCLUDED_OIL_RE = re.compile(
    r"\b(?:palm|olive|cooking|sunflower|vegetable|essential|coconut|canola|sesame|motor)\s+oil\b",
    re.IGNORECASE,
)


class RelevanceMatcher:
    """
    Compiles patterns once per asset run and provides match(title, summary) -> reason | None.
    """
    def __init__(
        self,
        asset: Asset,
        asset_kind: str,
        match_fn,
    ):
        self.asset = asset
        self.asset_kind = asset_kind
        self._match_fn = match_fn

    @classmethod
    def for_asset(cls, asset: Asset) -> "RelevanceMatcher":
        ticker = asset.ticker.strip()
        asset_type = asset.asset_type

        # Determine asset classification
        if asset_type == AssetType.FOREX or "/" in ticker or ticker.upper().endswith("=X"):
            return cls._compile_forex(asset)
        elif asset_type in (AssetType.COMMODITY, AssetType.FUTURES) or ticker.upper().endswith("=F"):
            return cls._compile_futures(asset)
        elif asset_type == AssetType.CRYPTO or ticker.upper().endswith("-USD"):
            return cls._compile_crypto(asset)
        else:
            return cls._compile_equity(asset)

    @classmethod
    def _compile_forex(cls, asset: Asset) -> "RelevanceMatcher":
        ticker = asset.ticker.strip().upper()
        clean = ticker.replace("=X", "")
        if "/" in clean:
            parts = clean.split("/", 1)
            base, quote = parts[0].strip(), parts[1].strip()
        elif "-" in clean:
            parts = clean.split("-", 1)
            base, quote = parts[0].strip(), parts[1].strip()
        elif len(clean) == 6:
            base, quote = clean[:3], clean[3:]
        else:
            base, quote = clean[:3], clean[3:] if len(clean) > 3 else ""

        our_pairs = {(base, quote), (quote, base)}

        # Compile pair pattern (EUR/USD, EURUSD, EUR-USD, EUR USD) in either order
        pair_pattern = re.compile(
            rf"\b(?:{re.escape(base)}[ /-]?{re.escape(quote)}|{re.escape(quote)}[ /-]?{re.escape(base)})\b",
            re.IGNORECASE,
        )

        # Currencies explicit pair pattern to find conflicting pairs
        known_cur_re = "|".join(KNOWN_CURRENCIES)
        explicit_pair_re = re.compile(
            rf"\b({known_cur_re})[/-]({known_cur_re})\b",
            re.IGNORECASE,
        )
        concatenated_pair_re = re.compile(
            rf"\b({known_cur_re})({known_cur_re})\b",
        )

        # Currency names
        base_names = CURRENCY_NAMES.get(base, ())
        quote_names = CURRENCY_NAMES.get(quote, ())

        def _make_currency_name_regex(names: tuple[str, ...]) -> re.Pattern | None:
            if not names:
                return None
            escaped = [re.escape(n) for n in names]
            return re.compile(rf"\b(?:{'|'.join(escaped)})\b", re.IGNORECASE)

        base_name_re = _make_currency_name_regex(base_names)
        quote_name_re = _make_currency_name_regex(quote_names)

        # For USD-quoted majors, non-USD leg name alone
        is_usd_major = (base == "USD" or quote == "USD") and bool(base and quote)
        other_code = quote if base == "USD" else base
        other_names = CURRENCY_NAMES.get(other_code, ())
        other_name_re = _make_currency_name_regex(other_names) if is_usd_major else None

        usd_name_re = re.compile(r"\b(?:dollar|dollars|greenback)\b", re.IGNORECASE)

        def match_forex(title: str, summary: str = "") -> MatchReason | None:
            combined = f"{title} {summary}"

            # 1. Check for conflicting explicit pairs
            found_pairs = set()
            for m in explicit_pair_re.finditer(combined):
                c1, c2 = m.group(1).upper(), m.group(2).upper()
                if c1 != c2:
                    found_pairs.add((c1, c2))
            for m in concatenated_pair_re.finditer(combined):
                c1, c2 = m.group(1).upper(), m.group(2).upper()
                if c1 != c2:
                    found_pairs.add((c1, c2))

            if found_pairs and not (found_pairs & our_pairs):
                # Text names a different explicit pair but not ours
                return None

            # 2. Pair in either notation
            if pair_pattern.search(combined):
                return "PAIR"

            # Prepare text for USD checks: strip non-USD dollar references
            sanitized_usd_text = NON_USD_DOLLAR_RE.sub(" ", combined)

            # 3. Both currency names
            if base == "USD" and quote_name_re:
                if usd_name_re.search(sanitized_usd_text) and quote_name_re.search(combined):
                    return "CURRENCY_NAMES"
            elif quote == "USD" and base_name_re:
                if usd_name_re.search(sanitized_usd_text) and base_name_re.search(combined):
                    return "CURRENCY_NAMES"
            elif base_name_re and quote_name_re:
                if base_name_re.search(combined) and quote_name_re.search(combined):
                    return "CURRENCY_NAMES"

            # 4. For USD-quoted majors:
            # - non-USD leg name alone ("yen", "euro", "sterling", "loonie", "aussie", "kiwi", "franc")
            # - or USD dollar alone (if sanitized text has USD dollar)
            if is_usd_major:
                if other_name_re and other_name_re.search(combined):
                    return "CURRENCY_NAMES"
                if usd_name_re.search(sanitized_usd_text):
                    return "CURRENCY_NAMES"

            return None

        return cls(asset=asset, asset_kind="FOREX", match_fn=match_forex)

    @classmethod
    def _compile_futures(cls, asset: Asset) -> "RelevanceMatcher":
        ticker = asset.ticker.strip().upper()
        keywords = FUTURES_KEYWORDS.get(ticker, ())
        company_name = asset.company_name.strip()

        has_oil = any(kw.lower() == "oil" for kw in keywords)
        other_kw_patterns: list[tuple[str, re.Pattern]] = [
            (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
            for kw in keywords if kw.lower() != "oil"
        ]
        oil_re = re.compile(r"\boil\b", re.IGNORECASE) if has_oil else None

        cashtag_re = re.compile(rf"\${re.escape(ticker)}\b", re.IGNORECASE)
        comp_re = re.compile(rf"\b{re.escape(company_name)}\b", re.IGNORECASE) if company_name else None

        def match_futures(title: str, summary: str = "") -> MatchReason | None:
            combined = f"{title} {summary}"

            if cashtag_re.search(combined):
                return "CASHTAG"

            for _, pat in other_kw_patterns:
                if pat.search(combined):
                    return "KEYWORD"

            if oil_re:
                # Strip excluded oils (palm oil, olive oil, etc.)
                clean_text = EXCLUDED_OIL_RE.sub(" ", combined)
                if oil_re.search(clean_text):
                    return "KEYWORD"

            if comp_re and comp_re.search(combined):
                return "NAME"

            return None

        return cls(asset=asset, asset_kind="FUTURES", match_fn=match_futures)

    @classmethod
    def _compile_crypto(cls, asset: Asset) -> "RelevanceMatcher":
        ticker = asset.ticker.strip().upper()
        symbol = ticker.split("-")[0]
        names = CRYPTO_NAMES.get(symbol, ())

        cashtag_re = re.compile(rf"\${re.escape(symbol)}\b", re.IGNORECASE)
        symbol_re = re.compile(rf"\b{re.escape(symbol)}\b")  # Case-sensitive bare symbol
        pair_re = re.compile(rf"\b{re.escape(symbol)}[ /-]USD\b", re.IGNORECASE)

        name_patterns = [
            re.compile(rf"\b{re.escape(n)}\b", re.IGNORECASE)
            for n in names
        ]

        def match_crypto(title: str, summary: str = "") -> MatchReason | None:
            combined = f"{title} {summary}"

            if cashtag_re.search(combined):
                return "CASHTAG"

            if pair_re.search(combined):
                return "PAIR"

            for pat in name_patterns:
                if pat.search(combined):
                    return "NAME"

            if symbol_re.search(combined):
                return "TICKER"

            return None

        return cls(asset=asset, asset_kind="CRYPTO", match_fn=match_crypto)

    @classmethod
    def _compile_equity(cls, asset: Asset) -> "RelevanceMatcher":
        ticker = asset.ticker.strip()
        norm_ticker = ticker.upper()
        company_name = asset.company_name.strip()

        # 1. Cashtag pattern
        cashtag_re = re.compile(rf"\${re.escape(ticker)}\b", re.IGNORECASE)

        # 2. Exchange-prefixed ticker
        exchange_re = re.compile(
            rf"\b(?:NASDAQ|NYSE|AMEX|BATS)\s*:\s*{re.escape(ticker)}\b",
            re.IGNORECASE,
        )

        # 3. Bare ticker (case-sensitive on original text, length >= 2, not in COMMON_WORD_TICKERS)
        is_common_word = norm_ticker in COMMON_WORD_TICKERS
        ticker_len_valid = len(ticker) >= 2
        # Support BRK-B matching BRK.B
        if "-" in ticker:
            alt_ticker = ticker.replace("-", ".")
            bare_ticker_pattern = rf"\b(?:{re.escape(ticker)}|{re.escape(alt_ticker)})\b"
        elif "." in ticker:
            alt_ticker = ticker.replace(".", "-")
            bare_ticker_pattern = rf"\b(?:{re.escape(ticker)}|{re.escape(alt_ticker)})\b"
        else:
            bare_ticker_pattern = rf"\b{re.escape(ticker)}\b"
        bare_ticker_re = re.compile(bare_ticker_pattern)

        # 4 & 5. Aliases
        alias_entry = EQUITY_ALIASES.get(norm_ticker)
        non_ambig_alias_res = []
        ambig_alias_res = []

        # Special case: AT&T for T
        if norm_ticker == "T" or "at&t" in company_name.lower():
            att_re = re.compile(r"\bat&t\b", re.IGNORECASE)
            non_ambig_alias_res.append(att_re)

        if alias_entry:
            for al in alias_entry.aliases:
                pat = re.compile(rf"\b{re.escape(al)}\b", re.IGNORECASE)
                if alias_entry.ambiguous:
                    ambig_alias_res.append(pat)
                else:
                    non_ambig_alias_res.append(pat)

        # Market context pattern for ambiguous aliases
        market_context_re = re.compile(
            rf"\b(?:{'|'.join(re.escape(t) for t in MARKET_CONTEXT_TERMS)})\b",
            re.IGNORECASE,
        )

        # 6. Full cleaned company name
        name_words = [
            w for w in re.findall(r"[a-zA-Z0-9]+", company_name)
            if w.lower() not in LEGAL_CORPORATE_SUFFIXES
        ]
        clean_company_name = " ".join(name_words).strip()
        is_ambiguous_single_word = (
            len(name_words) == 1
            and (
                (norm_ticker in EQUITY_ALIASES and EQUITY_ALIASES[norm_ticker].ambiguous)
                or name_words[0].upper() in COMMON_WORD_TICKERS
                or name_words[0].lower() in {"target", "gap", "visa", "ford", "shell"}
            )
        )

        full_name_re = None
        if clean_company_name and len(clean_company_name) >= 3:
            full_name_re = re.compile(rf"\b{re.escape(clean_company_name)}\b", re.IGNORECASE)

        # Full raw name if different
        full_raw_re = None
        if company_name and len(company_name) >= 3 and company_name.lower() != clean_company_name.lower():
            full_raw_re = re.compile(rf"\b{re.escape(company_name.strip())}\b", re.IGNORECASE)

        # 7. First distinctive name token, only in Title Case, not generic
        distinctive_token_re = None
        # Only search distinctive token if clean_company_name is not generic and not ambiguous single word
        if not is_ambiguous_single_word:
            for tok in name_words:
                if tok.lower() not in GENERIC_NAME_TOKENS and len(tok) >= 3:
                    # Require Title Case in original text (e.g. \bApple\b, \bTesla\b)
                    title_case_tok = tok.capitalize()
                    distinctive_token_re = re.compile(rf"\b{re.escape(title_case_tok)}\b")
                    break

        def match_equity(title: str, summary: str = "") -> MatchReason | None:
            combined = f"{title} {summary}"

            # 1. Cashtag
            if cashtag_re.search(combined):
                return "CASHTAG"

            # 2. Exchange-prefixed ticker
            if exchange_re.search(combined):
                return "EXCHANGE_TICKER"

            # 3. Bare ticker (case-sensitive, length >= 2, not common word)
            if ticker_len_valid and not is_common_word:
                if bare_ticker_re.search(combined):
                    return "TICKER"

            # 4. Non-ambiguous aliases
            for pat in non_ambig_alias_res:
                if pat.search(combined):
                    return "ALIAS"

            # 5. Ambiguous aliases with market context
            for pat in ambig_alias_res:
                if pat.search(combined):
                    if market_context_re.search(combined):
                        return "ALIAS"

            # 6. Full cleaned company name
            if full_name_re and full_name_re.search(combined):
                if is_ambiguous_single_word:
                    # Ambiguous single-word company name requires market context
                    if market_context_re.search(combined):
                        return "NAME"
                else:
                    return "NAME"

            if full_raw_re and full_raw_re.search(combined):
                return "NAME"

            # 7. First distinctive name token in Title Case
            if distinctive_token_re and distinctive_token_re.search(combined):
                return "NAME"

            return None

        return cls(asset=asset, asset_kind="EQUITY", match_fn=match_equity)

    def match(self, title: str, summary: str = "") -> MatchReason | None:
        """Evaluates relevance and returns MatchReason if relevant, else None."""
        return self._match_fn(title, summary)
