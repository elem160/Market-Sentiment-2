import asyncio
from unittest.mock import MagicMock

import pytest
from fakes import KeywordScorer

from app.core.enums import ProviderType
from app.core.models import IngestedArticle
from app.services.finbert_service import FinBERTService
from app.services.scoring import (
    ClassProbs,
    FinBERTScorer,
    SentimentScorer,
)


def test_scorer_protocol_conformance():
    """Verify FinBERTScorer and KeywordScorer conform to SentimentScorer protocol."""
    scorer = FinBERTScorer()
    assert isinstance(scorer, SentimentScorer)
    assert scorer.state == "NOT_LOADED"

    fake = KeywordScorer()
    assert isinstance(fake, SentimentScorer)
    assert fake.state == "LOADED"


def test_output_normalization():
    """Verify output normalization handles various pipeline output structures and label casing."""
    scorer = FinBERTScorer()

    # Standard nested list of dicts
    nested = [
        [
            {"label": "positive", "score": 0.85},
            {"label": "negative", "score": 0.05},
            {"label": "neutral", "score": 0.10},
        ],
        [
            {"label": "NEGATIVE", "score": 0.70},
            {"label": "POSITIVE", "score": 0.10},
            {"label": "NEUTRAL", "score": 0.20},
        ],
    ]
    res = scorer._normalize_output(nested, 2)
    assert len(res) == 2
    assert res[0] == ClassProbs(positive=0.85, negative=0.05, neutral=0.10)
    assert res[1] == ClassProbs(positive=0.10, negative=0.70, neutral=0.20)

    # Flat list of dicts for single item (some transformers versions)
    flat = [
        {"label": "positive", "score": 0.90},
        {"label": "negative", "score": 0.02},
        {"label": "neutral", "score": 0.08},
    ]
    res_flat = scorer._normalize_output(flat, 1)
    assert len(res_flat) == 1
    assert res_flat[0] == ClassProbs(positive=0.90, negative=0.02, neutral=0.08)

    # Direct dict fallback
    direct = {"positive": 0.15, "negative": 0.25, "neutral": 0.60}
    res_direct = scorer._normalize_output(direct, 1)
    assert len(res_direct) == 1
    assert res_direct[0] == ClassProbs(positive=0.15, negative=0.25, neutral=0.60)


@pytest.mark.asyncio
async def test_batched_chunk_scoring(monkeypatch):
    """Verify texts are scored in chunks of FINBERT_BATCH_SIZE."""
    from app.config import settings

    monkeypatch.setattr(settings, "FINBERT_BATCH_SIZE", 2)
    scorer = FinBERTScorer()
    scorer.state = "LOADED"

    mock_pipeline = MagicMock()
    # Return dummy output per chunk
    def dummy_pipeline(chunk, **kwargs):
        return [
            [
                {"label": "positive", "score": 0.8},
                {"label": "negative", "score": 0.1},
                {"label": "neutral", "score": 0.1},
            ]
            for _ in chunk
        ]

    mock_pipeline.side_effect = dummy_pipeline
    scorer._pipeline = mock_pipeline

    texts = ["headline 1", "headline 2", "headline 3", "headline 4", "headline 5"]
    results = await scorer.score(texts)

    assert len(results) == 5
    # 5 items with batch size 2 -> 3 chunks (2, 2, 1)
    assert mock_pipeline.call_count == 3
    chunk_sizes = [len(call.args[0]) for call in mock_pipeline.call_args_list]
    assert chunk_sizes == [2, 2, 1]


@pytest.mark.asyncio
async def test_inter_chunk_cancellation(monkeypatch):
    """Verify cancelling the scoring task raises CancelledError between chunks."""
    from app.config import settings

    monkeypatch.setattr(settings, "FINBERT_BATCH_SIZE", 1)
    scorer = FinBERTScorer()
    scorer.state = "LOADED"

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = [
        [
            {"label": "positive", "score": 0.5},
            {"label": "negative", "score": 0.2},
            {"label": "neutral", "score": 0.3},
        ]
    ]
    scorer._pipeline = mock_pipeline

    texts = ["text 1", "text 2", "text 3"]

    task = asyncio.create_task(scorer.score(texts))
    # Cancel task immediately so it halts cooperative execution
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_empty_texts_scoring():
    """Verify empty input returns empty list without invoking model."""
    scorer = FinBERTScorer()
    res = await scorer.score([])
    assert res == []


@pytest.mark.asyncio
async def test_scorer_failed_state():
    """Verify scorer in FAILED state raises RuntimeError."""
    scorer = FinBERTScorer()
    scorer.state = "FAILED"

    with pytest.raises(RuntimeError, match="FAILED state"):
        await scorer.score(["some headline"])


@pytest.mark.asyncio
async def test_pipeline_deps_scorer_injection():
    """Verify PipelineDeps injects custom scorer into FinBERTService."""
    custom_scorer = MagicMock()
    custom_scorer.score = MagicMock(
        return_value=asyncio.Future()
    )
    custom_scorer.score.return_value.set_result(
        [ClassProbs(positive=0.9, negative=0.05, neutral=0.05)]
    )

    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    art = IngestedArticle(
        article_id="art_dep",
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_url="https://reuters.com/dep",
        title="Injected scorer test headline",
        summary="Summary text",
        published_at_utc=now,
        retrieved_at_utc=now,
    )

    service = FinBERTService.get_instance()
    results = await service.score_articles_async([art], {}, scorer=custom_scorer)

    assert len(results) == 1
    assert results[0].finbert_positive == 0.9
    custom_scorer.score.assert_called_once()
    # Check lead_text built at source (title + summary, <= 500 chars)
    assert results[0].lead_text == "Injected scorer test headline. Summary text"
