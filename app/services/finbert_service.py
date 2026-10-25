import asyncio
import threading

from app.core.constants import DIRECTIONAL_THRESHOLD
from app.core.models import IngestedArticle, ScoredArticle
from app.services.deduplication_service import DeduplicationService
from app.services.scoring import ClassProbs, SentimentScorer, get_default_scorer


class FinBERTService:
    _instance: "FinBERTService | None" = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "FinBERTService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def get_status(cls) -> str:
        """Return truthful initialization status of the active SentimentScorer."""
        scorer = get_default_scorer()
        return getattr(scorer, "state", "NOT_LOADED")

    def _build_scored_articles(
        self,
        articles: list[IngestedArticle],
        lead_texts: list[str],
        probs_list: list[ClassProbs],
        cluster_map: dict[str, str],
    ) -> list[ScoredArticle]:
        scored_list: list[ScoredArticle] = []
        for i, art in enumerate(articles):
            lead_text = lead_texts[i]
            probs = probs_list[i] if i < len(probs_list) else ClassProbs(0.0, 0.0, 1.0)
            p_pos = probs.positive
            p_neg = probs.negative
            p_neu = probs.neutral

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
            inferred = bool(art.raw_provider_metadata.get("publisher_inferred", False))

            scored_list.append(
                ScoredArticle(
                    article_id=art.article_id,
                    provider=art.provider,
                    source_name=art.source_name,
                    canonical_publisher=canonical_pub,
                    publisher_inferred=inferred,
                    canonical_url=art.canonical_url,
                    title=art.title,
                    published_at_utc=art.published_at_utc,
                    lead_text=lead_text,
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

    def _batch_score_articles_sync(
        self,
        articles: list[IngestedArticle],
        cluster_map: dict[str, str],
        scorer: SentimentScorer | None = None,
    ) -> list[ScoredArticle]:
        """Synchronous batch scoring helper for sync tests/callers."""
        if not articles:
            return []
        active_scorer = scorer or get_default_scorer()
        lead_texts = [f"{art.title}. {art.summary}".strip()[:500] for art in articles]

        if callable(active_scorer):
            probs_list: list[ClassProbs] = []
            for t in lead_texts:
                res = active_scorer(t)
                if isinstance(res, ClassProbs):
                    probs_list.append(res)
                elif isinstance(res, dict):
                    probs_list.append(
                        ClassProbs(
                            positive=float(res.get("positive", 0.0)),
                            negative=float(res.get("negative", 0.0)),
                            neutral=float(res.get("neutral", 0.0)),
                        )
                    )
                else:
                    probs_list.append(ClassProbs(0.0, 0.0, 1.0))
        else:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as ex:
                    probs_list = ex.submit(asyncio.run, active_scorer.score(lead_texts)).result()
            else:
                probs_list = asyncio.run(active_scorer.score(lead_texts))

        return self._build_scored_articles(articles, lead_texts, probs_list, cluster_map)

    async def score_articles_async(
        self,
        articles: list[IngestedArticle],
        cluster_map: dict[str, str],
        scorer: SentimentScorer | None = None,
    ) -> list[ScoredArticle]:
        """Runs FinBERT inference using the injected or default SentimentScorer."""
        if not articles:
            return []
        active_scorer = scorer or get_default_scorer()
        lead_texts = [f"{art.title}. {art.summary}".strip()[:500] for art in articles]
        probs_list = await active_scorer.score(lead_texts)
        return self._build_scored_articles(articles, lead_texts, probs_list, cluster_map)
