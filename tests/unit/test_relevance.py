import json
import os

import pytest

from app.core.asset_registry import build_google_query_subject
from app.core.enums import AssetType
from app.core.models import Asset
from app.services.relevance import RelevanceMatcher

FIXTURE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "fixtures", "relevance_cases.json"
)

with open(FIXTURE_PATH, encoding="utf-8") as f:
    RELEVANCE_CASES = json.load(f)


@pytest.mark.parametrize("case", RELEVANCE_CASES, ids=lambda c: c["id"])
def test_relevance_matrix_case(case: dict):
    asset = Asset(
        ticker=case["ticker"],
        company_name=case["company_name"],
        exchange="",
        asset_type=AssetType(case["asset_type"]),
    )
    matcher = RelevanceMatcher.for_asset(asset)
    reason = matcher.match(case["title"], case["summary"])

    if case["expected_relevant"]:
        assert reason is not None, (
            f"Case '{case['id']}' failed: expected relevant match with reason '{case['expected_reason']}', "
            f"but got None for headline '{case['title']}'"
        )
        if case["expected_reason"] is not None:
            assert reason == case["expected_reason"], (
                f"Case '{case['id']}': expected match reason '{case['expected_reason']}', got '{reason}'"
            )
    else:
        assert reason is None, (
            f"Case '{case['id']}' failed: expected irrelevant (None), but got '{reason}' "
            f"for headline '{case['title']}'"
        )


def test_google_query_subject_builder():
    # Equities: ("Apple" OR AAPL)
    assert build_google_query_subject("AAPL", "Apple Inc.", AssetType.EQUITY) == '("Apple" OR AAPL)'
    assert build_google_query_subject("GOOGL", "Alphabet Inc.", AssetType.EQUITY) == '("Alphabet" OR GOOGL)'

    # Forex: ("EUR/USD" OR EURUSD)
    assert build_google_query_subject("EUR/USD", "Euro / US Dollar", AssetType.FOREX) == '("EUR/USD" OR EURUSD)'
    assert build_google_query_subject("USDJPY=X", "US Dollar / Japanese Yen", AssetType.FOREX) == '("USD/JPY" OR USDJPY)'

    # Futures: ("crude oil" OR WTI), ("gold" OR bullion)
    assert build_google_query_subject("CL=F", "Crude Oil", AssetType.COMMODITY) == '("crude oil" OR WTI)'
    assert build_google_query_subject("GC=F", "Gold", AssetType.COMMODITY) == '("gold" OR bullion)'
    assert build_google_query_subject("ES=F", "S&P 500 E-mini", AssetType.FUTURES) == '("S&P 500" OR SPX)'

    # Crypto: (Bitcoin OR BTC)
    assert build_google_query_subject("BTC-USD", "Bitcoin USD", AssetType.CRYPTO) == '(Bitcoin OR BTC)'
    assert build_google_query_subject("ETH-USD", "Ethereum USD", AssetType.CRYPTO) == '(Ethereum OR ETH)'
