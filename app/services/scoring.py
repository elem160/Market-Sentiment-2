import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.config import settings
from app.utils.logging import logger


@dataclass
class ClassProbs:
    positive: float
    negative: float
    neutral: float


@runtime_checkable
class SentimentScorer(Protocol):
    state: str  # "NOT_LOADED" | "LOADING" | "LOADED" | "FAILED"

    def load(self) -> None:
        ...

    async def score(self, texts: list[str]) -> list[ClassProbs]:
        ...


class FinBERTScorer:
    """Production SentimentScorer wrapping transformers pipeline with batched inference

    on a dedicated single-thread executor to serialise GPU/CPU compute across jobs.
    """

    _instance: "FinBERTScorer | None" = None
    _singleton_lock = threading.Lock()

    def __init__(self):
        self.state: str = "NOT_LOADED"
        self._pipeline = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="finbert")
        self._load_lock = threading.Lock()
        self._ready_event = threading.Event()

    @classmethod
    def get_instance(cls) -> "FinBERTScorer":
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (used in teardown/testing)."""
        with cls._singleton_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None

    def load(self) -> None:
        """Synchronously load tokenizer, model and pipeline inside the worker thread."""
        with self._load_lock:
            if self._pipeline is not None and self.state == "LOADED":
                return
            self.state = "LOADING"
            try:
                import torch
                from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

                if settings.FINBERT_TORCH_THREADS > 0:
                    torch.set_num_threads(settings.FINBERT_TORCH_THREADS)

                logger.info(f"Loading local FinBERT model ({settings.FINBERT_MODEL_NAME})...")
                tokenizer = AutoTokenizer.from_pretrained(settings.FINBERT_MODEL_NAME)
                model = AutoModelForSequenceClassification.from_pretrained(settings.FINBERT_MODEL_NAME)
                self._pipeline = pipeline(
                    "sentiment-analysis",
                    model=model,
                    tokenizer=tokenizer,
                    top_k=None,
                    device=-1,  # CPU inference
                )
                self.state = "LOADED"
                self._ready_event.set()
                logger.info("FinBERT model successfully loaded into memory.")
            except Exception as e:
                self.state = "FAILED"
                self._ready_event.set()
                logger.error(f"Failed to load FinBERT model: {e}")
                raise

    async def ensure_loaded(self) -> None:
        """Asynchronously trigger model load on the dedicated executor and await completion."""
        if self.state == "LOADED":
            return
        if self.state == "FAILED":
            raise RuntimeError("FinBERT model is in FAILED state.")
        if self.state == "NOT_LOADED":
            loop = asyncio.get_running_loop()
            loop.run_in_executor(self._executor, self.load)
        await self.wait_until_ready(timeout=float(settings.PIPELINE_TIMEOUT_SECONDS))

    async def wait_until_ready(self, timeout: float = 60.0) -> None:
        """Wait until the model transitions to LOADED or FAILED state."""
        if self.state == "LOADED":
            return
        if self.state == "FAILED":
            raise RuntimeError("FinBERT model failed to load.")

        loop = asyncio.get_running_loop()
        ready = await loop.run_in_executor(None, self._ready_event.wait, timeout)
        if not ready:
            raise TimeoutError(f"FinBERT model loading timed out after {timeout} seconds.")
        if self.state == "FAILED":
            raise RuntimeError("FinBERT model failed to load.")

    def _normalize_output(self, raw_output: Any, expected_count: int) -> list[ClassProbs]:
        """Normalize transformers pipeline output across versions and single/multi item shapes."""
        if expected_count == 1 and isinstance(raw_output, list) and raw_output and isinstance(raw_output[0], dict):
            items = [raw_output]
        elif isinstance(raw_output, list):
            items = raw_output
        elif isinstance(raw_output, dict):
            items = [[raw_output]]
        else:
            items = []

        results: list[ClassProbs] = []
        for item in items:
            pos, neg, neu = 0.0, 0.0, 0.0
            if isinstance(item, list):
                for entry in item:
                    if isinstance(entry, dict):
                        if "label" in entry:
                            lbl = str(entry.get("label", "")).lower()
                            score = float(entry.get("score", 0.0))
                            if lbl == "positive":
                                pos = score
                            elif lbl == "negative":
                                neg = score
                            elif lbl == "neutral":
                                neu = score
                        else:
                            pos = float(entry.get("positive", pos))
                            neg = float(entry.get("negative", neg))
                            neu = float(entry.get("neutral", neu))
            elif isinstance(item, dict):
                pos = float(item.get("positive", 0.0))
                neg = float(item.get("negative", 0.0))
                neu = float(item.get("neutral", 0.0))
            results.append(ClassProbs(positive=round(pos, 4), negative=round(neg, 4), neutral=round(neu, 4)))

        # Pad with neutral if count mismatch (safety fallback)
        while len(results) < expected_count:
            results.append(ClassProbs(positive=0.0, negative=0.0, neutral=1.0))
        return results[:expected_count]

    def _run_chunk_sync(self, chunk: list[str]) -> list[ClassProbs]:
        """Execute one batched inference call synchronously on the dedicated executor."""
        if self._pipeline is None:
            self.load()
        batch_size = max(1, settings.FINBERT_BATCH_SIZE)
        raw_output = self._pipeline(
            chunk,
            batch_size=batch_size,
            truncation=True,
            max_length=512,
        )
        return self._normalize_output(raw_output, len(chunk))

    async def score(self, texts: list[str]) -> list[ClassProbs]:
        """Batched scoring across texts in chunks of FINBERT_BATCH_SIZE with inter-chunk cancellation check."""
        if not texts:
            return []

        if self.state != "LOADED":
            await self.ensure_loaded()

        chunk_size = max(1, settings.FINBERT_BATCH_SIZE)
        loop = asyncio.get_running_loop()
        results: list[ClassProbs] = []

        for i in range(0, len(texts), chunk_size):
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise asyncio.CancelledError()

            chunk = texts[i : i + chunk_size]
            chunk_probs = await loop.run_in_executor(self._executor, self._run_chunk_sync, chunk)
            results.extend(chunk_probs)

            if task is not None and task.cancelling():
                raise asyncio.CancelledError()

        return results

    def shutdown(self) -> None:
        """Gracefully shut down the single-thread executor."""
        self._executor.shutdown(wait=False)


_default_scorer: SentimentScorer | None = None


def get_default_scorer() -> SentimentScorer:
    """Return the globally configured default SentimentScorer."""
    global _default_scorer
    if _default_scorer is None:
        _default_scorer = FinBERTScorer.get_instance()
    return _default_scorer


def set_default_scorer(scorer: SentimentScorer | None) -> None:
    """Set the globally configured default SentimentScorer (used in tests and lifespan)."""
    global _default_scorer
    _default_scorer = scorer
