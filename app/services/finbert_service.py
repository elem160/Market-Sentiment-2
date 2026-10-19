import asyncio
import threading
from typing import Callable
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from app.config import settings
from app.core.models import IngestedArticle, ScoredArticle
from app.services.deduplication_service import DeduplicationService
from app.utils.logging import logger


from app.core.constants import DIRECTIONAL_THRESHOLD

class FinBERTService:
    _instance: "FinBERTService | None" = None
    _lock = threading.Lock()
    _pipeline = None
    _tokenizer = None
    _is_mock: bool = False
    _mock_fn: Callable[[str], dict[str, float]] | None = None

    @classmethod
    def get_instance(cls) -> "FinBERTService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def set_mock_mode(cls, mock_fn: Callable[[str], dict[str, float]] | None = None):
        """Enable deterministic mock mode for testing without GPU/model download."""
        cls._is_mock = True
        cls._mock_fn = staticmethod(mock_fn) if mock_fn else None

    @classmethod
    def reset_mock_mode(cls):
        cls._is_mock = False
        cls._mock_fn = None

    def _ensure_model_loaded(self):
        if self._is_mock:
            return
        if self._pipeline is None:
            with self._lock:
                if self._pipeline is None:
                    logger.info(f"Loading local FinBERT model ({settings.FINBERT_MODEL_NAME})...")
                    try:
                        self._tokenizer = AutoTokenizer.from_pretrained(settings.FINBERT_MODEL_NAME)
                        model = AutoModelForSequenceClassification.from_pretrained(settings.FINBERT_MODEL_NAME)
                        # top_k=None ensures all 3 classes: positive, negative, neutral are returned
                        self._pipeline = pipeline(
                            "sentiment-analysis",
                            model=model,
                            tokenizer=self._tokenizer,
                            top_k=None,
                            device=-1  # CPU inference
                        )
                        logger.info("FinBERT model successfully loaded into memory.")
                    except Exception as e:
                        logger.error(f"Failed to load FinBERT model: {e}")
                        raise

    def _prepare_text(self, title: str, summary: str) -> str:
        """Tokenize text and truncate strictly to 512 tokens using FinBERT tokenizer."""
        combined = f"{title}. {summary}".strip()
        if self._is_mock or self._tokenizer is None:
            # Word slicing fallback for mock mode
            words = combined.split()[:250]
            return " ".join(words)[:1200]
        
        tokens = self._tokenizer.encode(combined, max_length=512, truncation=True)
        return self._tokenizer.decode(tokens, skip_special_tokens=True)

    def _score_single_text_sync(self, text: str) -> dict[str, float]:
        """Synchronous score of a single text returning {positive, negative, neutral} probabilities."""
        if self._is_mock:
            if FinBERTService._mock_fn is not None:
                fn = FinBERTService._mock_fn
                if hasattr(fn, "__func__"):
                    fn = fn.__func__
                return fn(text)
            # Default mock rule: check word tokens cleanly
            import re
            lower = text.lower()
            tokens = set(re.findall(r"\b[a-z]+\b", lower))
            pos_words = {"beat", "record", "growth", "surge", "gain", "profit", "bull", "rally", "outperform", "robust"}
            neg_words = {"miss", "fall", "drop", "loss", "decline", "bear", "lawsuit", "slashes", "cut", "warned", "restrictions"}

            if tokens & neg_words and not (tokens & pos_words):
                return {"positive": 0.05, "negative": 0.85, "neutral": 0.10}
            elif tokens & pos_words and not (tokens & neg_words):
                return {"positive": 0.85, "negative": 0.05, "neutral": 0.10}
            elif tokens & neg_words:
                return {"positive": 0.05, "negative": 0.85, "neutral": 0.10}
            elif tokens & pos_words:
                return {"positive": 0.85, "negative": 0.05, "neutral": 0.10}
            else:
                return {"positive": 0.10, "negative": 0.10, "neutral": 0.80}

        self._ensure_model_loaded()
        results = self._pipeline(text)[0]  # List of dicts: [{'label': 'positive', 'score': 0.88}, ...]
        scores: dict[str, float] = {}
        for r in results:
            scores[r["label"].lower()] = round(float(r["score"]), 4)
        return scores

    def _batch_score_articles_sync(
        self, articles: list[IngestedArticle], cluster_map: dict[str, str]
    ) -> list[ScoredArticle]:
        """Runs batch FinBERT inference synchronously across all articles."""
        scored_list: list[ScoredArticle] = []

        for art in articles:
            prepared_lead = self._prepare_text(art.title, art.summary)
            scores = self._score_single_text_sync(prepared_lead)

            p_pos = scores.get("positive", 0.0)
            p_neg = scores.get("negative", 0.0)
            p_neu = scores.get("neutral", 0.0)

            # Directional Score formula: P(pos) - P(neg) in [-1.0, 1.0]
            diff = round(p_pos - p_neg, 4)
            confidence = round(max(p_pos, p_neg), 4)

            # Neutral Rule (F-12):
            # If absolute directional difference is below threshold, article is neutral (0.0 score, 0.0 weight).
            # If >= threshold, score is diff and weight is proportional to confidence * (1.0 - p_neu).
            if abs(diff) < DIRECTIONAL_THRESHOLD:
                directional_score = 0.0
                initial_weight = 0.0
            else:
                directional_score = diff
                initial_weight = round(confidence * (1.0 - p_neu), 4)

            canonical_pub = DeduplicationService.normalize_publisher(art.source_name)
            cluster_id = cluster_map.get(art.article_id, f"clust_{art.article_id[:8]}")

            scored_list.append(
                ScoredArticle(
                    article_id=art.article_id,
                    provider=art.provider,
                    source_name=art.source_name,
                    canonical_publisher=canonical_pub,
                    canonical_url=art.canonical_url,
                    title=art.title,
                    published_at_utc=art.published_at_utc,
                    lead_text=prepared_lead,
                    finbert_positive=p_pos,
                    finbert_negative=p_neg,
                    finbert_neutral=p_neu,
                    finbert_directional_score=directional_score,
                    finbert_confidence=confidence,
                    is_llm_catalyst=False,
                    catalyst_category=None,
                    exclusion_reason=None,
                    final_weight=initial_weight,
                    cluster_id=cluster_id,
                )
            )

        return scored_list

    async def score_articles_async(
        self, articles: list[IngestedArticle], cluster_map: dict[str, str]
    ) -> list[ScoredArticle]:
        """
        Runs FinBERT inference offloaded to a worker thread pool via asyncio.to_thread,
        preventing any blocking of FastAPI's async event loop.
        """
        if not articles:
            return []
        return await asyncio.to_thread(self._batch_score_articles_sync, articles, cluster_map)
