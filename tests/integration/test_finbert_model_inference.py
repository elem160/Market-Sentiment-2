from datetime import datetime, timezone

import pytest

from app.core.enums import ProviderType
from app.core.models import IngestedArticle
from app.services.finbert_service import FinBERTService


@pytest.mark.slow
@pytest.mark.asyncio
async def test_real_finbert_model_inference():
    """Slow integration test executing real ProsusAI/finbert model weights."""
    now = datetime.now(timezone.utc)
    art_pos = IngestedArticle(
        article_id="real_pos",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://example.com/pos",
        title="NVIDIA reports blockbuster quarterly earnings exceeding all forecasts",
        summary="Company profits surged 200% year over year.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    art_neg = IngestedArticle(
        article_id="real_neg",
        provider=ProviderType.YFINANCE,
        source_name="Bloomberg",
        canonical_url="https://example.com/neg",
        title="Company files for bankruptcy following massive accounting fraud and steep losses",
        summary="Creditors plan liquidation of remaining assets.",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    service = FinBERTService.get_instance()
    scored = await service.score_articles_async([art_pos, art_neg], {})

    assert len(scored) == 2
    # art_pos should be clearly positive
    assert scored[0].finbert_positive > scored[0].finbert_negative
    assert scored[0].finbert_directional_score > 0.0

    # art_neg should be clearly negative
    assert scored[1].finbert_negative > scored[1].finbert_positive
    assert scored[1].finbert_directional_score < 0.0
