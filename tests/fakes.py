"""Deterministic test doubles shared by the suite (injected through dependency injection from Phase 3)."""
import asyncio
import re
from collections.abc import Iterable
from types import SimpleNamespace
from typing import Any

POSITIVE_WORDS = frozenset(
    {"beat", "record", "growth", "surge", "gain", "profit", "bull", "rally", "outperform", "robust"}
)
NEGATIVE_WORDS = frozenset(
    {"miss", "fall", "drop", "loss", "decline", "bear", "lawsuit", "slashes", "cut", "warned", "restrictions"}
)

POSITIVE_PROBS = {"positive": 0.85, "negative": 0.05, "neutral": 0.10}
NEGATIVE_PROBS = {"positive": 0.05, "negative": 0.85, "neutral": 0.10}
NEUTRAL_PROBS = {"positive": 0.10, "negative": 0.10, "neutral": 0.80}


class KeywordScorer:
    """Stand-in for FinBERT: classifies text with keyword lists; negative words win when both appear."""

    def __init__(
        self,
        positive_words: Iterable[str] = POSITIVE_WORDS,
        negative_words: Iterable[str] = NEGATIVE_WORDS,
    ):
        self.positive_words = frozenset(positive_words)
        self.negative_words = frozenset(negative_words)

    def __call__(self, text: str) -> dict[str, float]:
        tokens = set(re.findall(r"\b[a-z]+\b", text.lower()))
        if tokens & self.negative_words:
            return dict(NEGATIVE_PROBS)
        if tokens & self.positive_words:
            return dict(POSITIVE_PROBS)
        return dict(NEUTRAL_PROBS)


def make_completion(
    content: str | None,
    *,
    finish_reason: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    model: str = "fake/model",
) -> SimpleNamespace:
    """Build an object shaped like an ``openai`` ChatCompletion."""
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                index=0,
                finish_reason=finish_reason,
                message=SimpleNamespace(role="assistant", content=content),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


class FakeLLMClient:
    """Stand-in for ``openai.AsyncOpenAI`` exposing ``chat.completions.create()``.

    Replies are consumed in order: a completion object (see ``make_completion``) is returned,
    a ``str`` is wrapped into a completion and an exception instance is raised. ``delay``
    simulates latency; every request's keyword arguments are recorded in ``calls``.
    """

    def __init__(self, *replies: Any, delay: float = 0.0):
        self._replies = list(replies)
        self.delay = delay
        self.calls: list[dict[str, Any]] = []
        self.closed = False
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def queue(self, *replies: Any) -> None:
        self._replies.extend(replies)

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay:
            await asyncio.sleep(self.delay)
        if not self._replies:
            raise AssertionError("FakeLLMClient received a request but has no reply queued")
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, str):
            return make_completion(reply)
        return reply

    async def close(self) -> None:
        self.closed = True
