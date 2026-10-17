import pytest
from datetime import datetime, timezone
from app.services.finbert_service import FinBERTService
from app.core.models import IngestedArticle
from app.core.enums import ProviderType


@pytest.mark.asyncio
async def test_finbert_scoring_positive_and_negative():
    finbert = FinBERTService.get_instance()
    now = datetime.now(timezone.utc)

    # 1. Positive headline
    art_pos = IngestedArticle(
        article_id="pos_1",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/pos",
        title="Apple reports massive earnings beat and record revenue growth",
        summary="Profit surged beyond high-end analyst projections.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    # 2. Negative headline
    art_neg = IngestedArticle(
        article_id="neg_1",
        provider=ProviderType.YFINANCE,
        source_name="Wall Street Journal",
        canonical_url="https://wsj.com/neg",
        title="Nvidia shares drop sharply as export restrictions force guidance cut",
        summary="Management warned of severe supply chain disruptions and revenue decline.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    # 3. Neutral headline
    art_neu = IngestedArticle(
        article_id="neu_1",
        provider=ProviderType.YFINANCE,
        source_name="Bloomberg",
        canonical_url="https://bloomberg.com/neu",
        title="Tesla schedules annual shareholder meeting for November",
        summary="The proxy statement lists standard agenda items for voting.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    results = await finbert.score_articles_async([art_pos, art_neg, art_neu], {})
    assert len(results) == 3

    # Check Positive Article
    res_pos = results[0]
    assert res_pos.finbert_positive > res_pos.finbert_negative
    assert res_pos.finbert_directional_score > 0.5
    assert res_pos.final_weight > 0.5

    # Check Negative Article
    res_neg = results[1]
    assert res_neg.finbert_negative > res_neg.finbert_positive
    assert res_neg.finbert_directional_score < -0.5
    assert res_neg.final_weight > 0.5

    # Check Neutral Article Zero-Weighting
    res_neu = results[2]
    assert res_neu.finbert_neutral >= 0.60
    assert res_neu.finbert_directional_score == 0.0
    assert res_neu.final_weight == 0.0


def test_neutral_zero_weighting_rule():
    finbert = FinBERTService.get_instance()
    # Configure custom mock function returning high neutral
    FinBERTService.set_mock_mode(lambda text: {"positive": 0.20, "negative": 0.15, "neutral": 0.65})

    now = datetime.now(timezone.utc)
    art = IngestedArticle(
        article_id="test_neu",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/test",
        title="Company files standard quarterly 10-Q report",
        summary="Routine filing without revision.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    results = finbert._batch_score_articles_sync([art], {})
    assert len(results) == 1
    scored = results[0]

    assert scored.finbert_neutral == 0.65
    assert scored.finbert_directional_score == 0.0
    assert scored.final_weight == 0.0
