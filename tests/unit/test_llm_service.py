import asyncio
import pytest
from unittest.mock import patch
from datetime import datetime, timezone

from app.config import settings
from app.services.llm_service import LLMService, sanitize_text
from app.core.models import ScoredArticle
from app.core.enums import ProviderType, CatalystCategory
from fakes import FakeLLMClient, make_completion


@pytest.fixture(autouse=True)
def enable_llm(monkeypatch):
    """The suite disables the LLM globally; these unit tests switch it on (the client is always a fake)."""
    monkeypatch.setattr(settings, "ENABLE_LLM", True)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "test_key")


def create_candidate(art_id: str, score: float, conf: float) -> ScoredArticle:
    now = datetime.now(timezone.utc)
    return ScoredArticle(
        article_id=art_id,
        provider=ProviderType.YFINANCE,
        source_name="Reuters",
        canonical_publisher="Reuters",
        canonical_url=f"https://reuters.com/{art_id}",
        title=f"Sample title {art_id}",
        published_at_utc=now,
        lead_text=f"Lead text for {art_id}",
        finbert_positive=score if score > 0 else 0.05,
        finbert_negative=abs(score) if score < 0 else 0.05,
        finbert_neutral=0.1,
        finbert_directional_score=score,
        finbert_confidence=conf,
        is_llm_catalyst=False,
        catalyst_category=None,
        exclusion_reason=None,
        final_weight=conf,
        cluster_id=f"c_{art_id}",
    )


@pytest.mark.asyncio
async def test_llm_single_batch_catalyst_verification():
    art1 = create_candidate("art_valid", 0.85, 0.90)
    art2 = create_candidate("art_speculation", 0.40, 0.50)
    service = LLMService()

    service.client = FakeLLMClient(
        make_completion(
            '''{
                "catalysts": [{"index": 1, "category": "EARNINGS"}],
                "catalyst_indices": [1, 99],
                "synthesis_summary": "Strong earnings reported with record quarterly revenues."
            }''',
            prompt_tokens=250,
            completion_tokens=80,
        )
    )

    updated_arts, facts, summary, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art1, art2])

    assert updated_arts[0].is_llm_catalyst is True
    assert updated_arts[0].catalyst_category == CatalystCategory.EARNINGS
    assert updated_arts[0].final_weight == pytest.approx(0.90 * 1.25, 0.01)
    assert len(facts) == 1
    assert facts[0].cited_article_id == "art_valid"
    assert facts[0].statement == art1.title

    assert updated_arts[1].is_llm_catalyst is False
    assert "Strong earnings" in summary
    assert telemetry["status"] == "SUCCESS"
    assert telemetry["prompt_tokens"] == 250
    assert telemetry["completion_tokens"] == 80
    assert telemetry["candidates_sent"] == 2


@pytest.mark.asyncio
async def test_llm_empty_catalyst_indices():
    art1 = create_candidate("art_noise", 0.30, 0.40)
    service = LLMService()
    service.client = FakeLLMClient(
        make_completion(
            '''{
                "catalysts": [],
                "catalyst_indices": [],
                "synthesis_summary": "No material catalysts observed in current headlines."
            }''',
            prompt_tokens=150,
            completion_tokens=30,
        )
    )

    updated_arts, facts, summary, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art1])

    assert updated_arts[0].is_llm_catalyst is False
    assert len(facts) == 0
    assert telemetry["status"] == "SUCCESS"
    assert telemetry["candidates_sent"] == 1


@pytest.mark.asyncio
async def test_llm_slow_client_timeout_degrades_to_failed():
    """Verify H6: Overall deadline timeout marks status FAILED and does not crash the pipeline."""
    art = create_candidate("art_slow", 0.80, 0.85)
    service = LLMService()
    # Fake client with 0.2s latency, but deadline is 0.03s
    service.client = FakeLLMClient(
        make_completion('{"catalysts": [], "synthesis_summary": "Late"}'),
        delay=0.2,
    )

    with patch("app.config.settings.LLM_TIMEOUT_SECONDS", 0.03):
        updated_arts, facts, summary, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art])
        assert telemetry["status"] == "FAILED"
        assert telemetry["reason"] == "TIMEOUT"
        assert len(facts) == 0
        assert summary == ""


@pytest.mark.asyncio
async def test_no_hardcoded_fallback_model():
    """Verify H7: Only LLM_MODEL_ID and LLM_FALLBACK_MODEL_ID are attempted; no hardcoded fallbacks."""
    art = create_candidate("art_1", 0.80, 0.85)
    service = LLMService()
    client = FakeLLMClient(
        Exception("Primary failed"),
        make_completion('{"catalysts": [], "synthesis_summary": "Fallback worked"}'),
    )
    service.client = client

    with patch("app.config.settings.LLM_MODEL_ID", "provider/model-primary"), \
         patch("app.config.settings.LLM_FALLBACK_MODEL_ID", "provider/model-fallback"):
        _, _, _, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art])
        assert telemetry["status"] == "SUCCESS"
        assert telemetry["model"] == "provider/model-fallback"
        assert [c["model"] for c in client.calls] == ["provider/model-primary", "provider/model-fallback"]

    # When fallback is empty, only primary is attempted
    client2 = FakeLLMClient(Exception("Primary failed"))
    service.client = client2
    with patch("app.config.settings.LLM_MODEL_ID", "provider/model-primary"), \
         patch("app.config.settings.LLM_FALLBACK_MODEL_ID", ""):
        _, _, _, telemetry2 = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art])
        assert telemetry2["status"] == "FAILED"
        assert [c["model"] for c in client2.calls] == ["provider/model-primary"]


@pytest.mark.asyncio
async def test_finish_reason_length_tries_next_model():
    """Verify H7: finish_reason='length' fails the attempt and moves to the next model."""
    art = create_candidate("art_1", 0.80, 0.85)
    service = LLMService()
    client = FakeLLMClient(
        make_completion('{"catalysts": [{"index": 1', finish_reason="length"),
        make_completion('{"catalysts": [{"index": 1, "category": "MACRO"}], "synthesis_summary": "Macro move."}'),
    )
    service.client = client

    with patch("app.config.settings.LLM_MODEL_ID", "primary/model"), \
         patch("app.config.settings.LLM_FALLBACK_MODEL_ID", "secondary/model"):
        _, facts, summary, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art])
        assert telemetry["status"] == "SUCCESS"
        assert telemetry["model"] == "secondary/model"
        assert len(facts) == 1
        assert telemetry["attempts"][0]["outcome"] == "FAILED_LENGTH"
        assert telemetry["attempts"][1]["outcome"] == "SUCCESS"


@pytest.mark.asyncio
async def test_invalid_json_tries_next_model_or_fails():
    """Verify invalid JSON fails attempt and moves to next model."""
    art = create_candidate("art_1", 0.80, 0.85)
    service = LLMService()
    client = FakeLLMClient(
        make_completion("This is conversational text without any JSON."),
        make_completion('{"catalysts": [], "synthesis_summary": "Valid fallback"}'),
    )
    service.client = client

    with patch("app.config.settings.LLM_MODEL_ID", "primary/model"), \
         patch("app.config.settings.LLM_FALLBACK_MODEL_ID", "secondary/model"):
        _, facts, summary, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art])
        assert telemetry["status"] == "SUCCESS"
        assert telemetry["model"] == "secondary/model"
        assert telemetry["attempts"][0]["outcome"] == "FAILED_INVALID_JSON"


def test_prompt_sanitization_order_and_control_chars():
    """Verify M10: & is escaped first, then < and >, control characters are stripped, and lengths capped."""
    raw = "AT&T \x00\x08<Break> & New \x1fProducts"
    sanitized = sanitize_text(raw, max_chars=100)
    assert "\x00" not in sanitized
    assert "\x08" not in sanitized
    assert "\x1f" not in sanitized
    assert "&amp;" in sanitized
    assert "&lt;Break&gt;" in sanitized
    assert "&amp;lt;" not in sanitized  # & must not double-escape the entity tags

    # Length capping
    long_text = "A" * 300
    assert len(sanitize_text(long_text, max_chars=200)) == 200


@pytest.mark.asyncio
async def test_max_prompt_tokens_trimming():
    """Verify MAX_PROMPT_TOKENS drops lowest confidence candidates until within limit."""
    art1 = create_candidate("art_high", 0.90, 0.95)
    art2 = create_candidate("art_med", 0.70, 0.75)
    art3 = create_candidate("art_low", 0.50, 0.55)

    service = LLMService()
    client = FakeLLMClient(make_completion('{"catalysts": [], "synthesis_summary": "Done"}'))
    service.client = client

    # Set very tight MAX_PROMPT_TOKENS so that 3 candidates exceed it, forcing trimming
    with patch("app.config.settings.MAX_PROMPT_TOKENS", 250):
        _, _, _, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art1, art2, art3])
        assert telemetry["candidates_sent"] < 3
        user_prompt = client.calls[0]["messages"][1]["content"]
        assert "art_high" in user_prompt


@pytest.mark.asyncio
async def test_per_model_budget_cap_skip():
    """Verify expensive model is skipped per-model while affordable fallback is called."""
    art = create_candidate("art_1", 0.80, 0.85)
    service = LLMService()
    client = FakeLLMClient(
        make_completion('{"catalysts": [], "synthesis_summary": "Affordable run"}')
    )
    service.client = client

    # Primary costs $0.10 (exceeds $0.05 budget), fallback is free ($0.00)
    def mock_cost(model, prompt_tokens, comp_tokens):
        if model == "expensive/model":
            return 0.10
        return 0.00

    with patch("app.config.settings.LLM_MODEL_ID", "expensive/model"), \
         patch("app.config.settings.LLM_FALLBACK_MODEL_ID", "free/model:free"), \
         patch("app.config.settings.MAX_COST_PER_RUN_USD", 0.05), \
         patch("app.config.Settings.estimate_cost", side_effect=mock_cost):
        _, _, _, telemetry = await service.verify_and_synthesize("AAPL", "Apple Inc.", [art])
        assert telemetry["status"] == "SUCCESS"
        assert telemetry["model"] == "free/model:free"
        assert telemetry["attempts"][0]["outcome"] == "SKIPPED_BUDGET_CAP"
        assert [c["model"] for c in client.calls] == ["free/model:free"]


@pytest.mark.asyncio
async def test_client_closed_on_shutdown():
    """Verify close_client safely closes the shared client and resets it to None."""
    fake_client = FakeLLMClient()
    LLMService._shared_client = fake_client

    await LLMService.close_client()
    assert fake_client.closed is True
    assert LLMService._shared_client is None
