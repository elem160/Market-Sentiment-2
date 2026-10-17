import hashlib
import time
import uuid
from typing import Callable, Awaitable
from sqlalchemy.orm import Session
from app.config import settings
from app.core.models import (
    AnalysisResult,
    PipelineMetrics,
    ScoredArticle,
)
from app.core.enums import PipelineStage, PipelineMode, CacheStatus
from app.core.session_window import compute_session_window
from app.services.ticker_service import TickerService
from app.services.news_service import NewsService
from app.services.deduplication_service import DeduplicationService
from app.services.finbert_service import FinBERTService
from app.services.llm_service import LLMService
from app.services.aggregator_service import AggregatorService
from app.db.repository import SentimentRepository
from app.utils.logging import logger

ProgressCallback = Callable[[PipelineStage, float, str], Awaitable[None]]


class AnalysisOrchestrator:
    @staticmethod
    def compute_cache_key(
        ticker: str,
        session_bucket: str,
        provider_hash: str,
        enable_llm: bool,
    ) -> str:
        """Deterministic multi-dimensional cache key."""
        config_hash = settings.get_config_hash()
        raw = f"{ticker}:{session_bucket}:{provider_hash}:{settings.FINBERT_MODEL_NAME}:{settings.LLM_MODEL_ID}:{config_hash}:{enable_llm}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    async def run_pipeline(
        cls,
        ticker: str,
        db: Session,
        force_refresh: bool = False,
        enable_llm: bool = True,
        on_progress: ProgressCallback | None = None,
    ) -> AnalysisResult:
        """
        Executes the 6-stage analysis pipeline with live progress reporting:
        Stage 1: Ticker Resolution
        Stage 2: News Ingestion (Session Window)
        Stage 3: Deduplication & Relevance Filtering
        Stage 4: Local FinBERT Classification (512 tokens, top_k=None)
        Stage 5: LLM Catalyst Verification (XML Shield & Citation Audit)
        Stage 6: Score Aggregation & Heuristic Decision Rules
        """
        t_start = time.time()
        stage_latencies: dict[str, float] = {}

        # ---------------------------------------------------------------------
        # Stage 1: Ticker Resolution & Session Window
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.RESOLVING_TICKER, 0.15, "Resolving ticker and company profile...")
        
        t0 = time.time()
        asset = TickerService.validate_and_resolve(ticker)
        session = compute_session_window()
        stage_latencies["resolving_ticker"] = round((time.time() - t0) * 1000, 1)

        # Multi-dimensional cache key calculation
        session_bucket = f"{session.session_type.value}_{session.window_start_et.strftime('%Y%m%d%H')}"
        provider_hash = "yfinance_finnhub_rss"
        cache_key = cls.compute_cache_key(asset.ticker, session_bucket, provider_hash, enable_llm)

        # Check Cache
        if not force_refresh:
            cached_result = SentimentRepository.get_cached_run(db, cache_key)
            if cached_result:
                logger.info(f"Cache hit for ticker {asset.ticker} (Key: {cache_key[:12]}...)")
                if on_progress:
                    await on_progress(PipelineStage.DONE, 1.0, "Loaded from cache.")
                return cached_result

        # ---------------------------------------------------------------------
        # Stage 2: News Ingestion & Session Window Filtering
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.INGESTING_NEWS, 0.35, f"Ingesting current-day news ({session.window_duration_hours}h session window)...")

        t1 = time.time()
        raw_articles, provider_outcomes = await NewsService.fetch_news_for_session(
            asset.ticker,
            asset.company_name,
            session,
            asset_type=asset.asset_type,
            yf_symbol=asset.yf_symbol,
        )
        stage_latencies["ingesting_news"] = round((time.time() - t1) * 1000, 1)

        # ---------------------------------------------------------------------
        # Stage 3: Deduplication, URL Cleaning & Relevance Filtering
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.FILTERING_DEDUPLICATING, 0.55, f"Deduplicating {len(raw_articles)} articles and filtering relevance...")

        t2 = time.time()
        retained_articles, excluded_articles, cluster_map = DeduplicationService.process_and_deduplicate(
            raw_articles, asset.ticker, asset.company_name
        )
        stage_latencies["filtering_deduplicating"] = round((time.time() - t2) * 1000, 1)

        # ---------------------------------------------------------------------
        # Stage 4: Local FinBERT Sentiment Classification
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.FINBERT_SCORING, 0.70, f"Running local FinBERT inference on {len(retained_articles)} candidate articles...")

        t3 = time.time()
        finbert_service = FinBERTService.get_instance()
        scored_retained = await finbert_service.score_articles_async(retained_articles, cluster_map)
        stage_latencies["finbert_scoring"] = round((time.time() - t3) * 1000, 1)

        # Build complete article evidence list (retained + excluded)
        complete_article_list: list[ScoredArticle] = list(scored_retained)
        for excl_art, reason, note in excluded_articles:
            canonical_pub = DeduplicationService.normalize_publisher(excl_art.source_name)
            complete_article_list.append(
                ScoredArticle(
                    article_id=excl_art.article_id,
                    provider=excl_art.provider,
                    source_name=excl_art.source_name,
                    canonical_publisher=canonical_pub,
                    canonical_url=excl_art.canonical_url,
                    title=excl_art.title,
                    published_at_utc=excl_art.published_at_utc,
                    lead_text=excl_art.summary[:500],
                    finbert_positive=0.0,
                    finbert_negative=0.0,
                    finbert_neutral=1.0,
                    finbert_directional_score=0.0,
                    finbert_confidence=0.0,
                    is_llm_catalyst=False,
                    catalyst_category=None,
                    exclusion_reason=reason,
                    final_weight=0.0,
                    cluster_id=cluster_map.get(excl_art.article_id, ""),
                )
            )

        # ---------------------------------------------------------------------
        # Stage 5: Gated LLM Catalyst Verification & Synthesis
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.CATALYST_SYNTHESIS, 0.85, "Verifying market catalysts via structured LLM prompt...")

        t4 = time.time()
        llm_service = LLMService()
        observed_facts = []
        llm_summary = ""
        llm_telemetry = {}
        pipeline_mode = PipelineMode.HYBRID_FINBERT_LLM

        if enable_llm and settings.ENABLE_LLM and settings.OPENROUTER_API_KEY:
            scored_retained, observed_facts, llm_summary, llm_telemetry = await llm_service.verify_and_synthesize(
                asset.ticker, asset.company_name, scored_retained
            )
            if llm_telemetry.get("status") in {"SKIPPED", "FAILED"}:
                pipeline_mode = PipelineMode.DETERMINISTIC_FINBERT_ONLY
        else:
            pipeline_mode = PipelineMode.DETERMINISTIC_FINBERT_ONLY

        stage_latencies["catalyst_synthesis"] = round((time.time() - t4) * 1000, 1)

        # ---------------------------------------------------------------------
        # Stage 6: Score Aggregation & Heuristic Decision Rules
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.AGGREGATING_DECISION, 0.95, "Synthesizing sentiment score and corroboration rules...")

        t5 = time.time()
        decision, confidence, score, quality, rationale, warnings = AggregatorService.aggregate_and_decide(
            asset.ticker,
            asset.company_name,
            session,
            scored_retained,
            observed_facts,
            llm_summary,
            pipeline_mode=pipeline_mode,
        )
        stage_latencies["aggregating_decision"] = round((time.time() - t5) * 1000, 1)

        # Compute summary metrics
        total_latency_ms = round((time.time() - t_start) * 1000, 1)
        distinct_publishers = len({
            a.canonical_publisher for a in scored_retained
            if a.canonical_publisher != "Unknown Aggregator" and a.exclusion_reason is None
        })
        distinct_clusters = len({
            a.cluster_id for a in scored_retained
            if a.cluster_id and a.exclusion_reason is None
        })

        metrics = PipelineMetrics(
            total_sources=len(provider_outcomes),
            distinct_publishers=distinct_publishers,
            distinct_clusters=distinct_clusters,
            articles_ingested=len(raw_articles),
            articles_retained=len(scored_retained),
            articles_deduplicated=len(excluded_articles),
            articles_scored_local=len(scored_retained),
            articles_sent_to_llm=min(settings.MAX_LLM_CANDIDATES, len([a for a in scored_retained if abs(a.finbert_directional_score) >= 0.15 and a.exclusion_reason is None])),
            prompt_tokens=llm_telemetry.get("prompt_tokens", 0),
            completion_tokens=llm_telemetry.get("completion_tokens", 0),
            estimated_cost_usd=llm_telemetry.get("estimated_cost_usd", 0.0),
            total_latency_ms=total_latency_ms,
            stage_latencies=stage_latencies,
        )

        run_id = str(uuid.uuid4())
        model_versions = {
            "finbert": settings.FINBERT_MODEL_NAME,
            "llm": settings.LLM_MODEL_ID if pipeline_mode == PipelineMode.HYBRID_FINBERT_LLM else "NONE",
        }

        result = AnalysisResult(
            run_id=run_id,
            ticker=asset.ticker,
            company_name=asset.company_name,
            asset_type=asset.asset_type,
            session=session,
            decision=decision,
            decision_confidence=confidence,
            sentiment_score=score,
            evidence_quality=quality,
            disclaimer="Research & Market Sentiment Tool. Not Financial or Investment Advice.",
            rationale=rationale,
            metrics=metrics,
            articles=complete_article_list,
            warnings=warnings,
            pipeline_mode=pipeline_mode,
            cache_status=CacheStatus.MISS,
            model_versions=model_versions,
            config_version=settings.get_config_hash(),
        )

        # Persist run and evidence in database
        SentimentRepository.save_analysis_run(db, result, cache_key, provider_outcomes)

        if on_progress:
            await on_progress(PipelineStage.DONE, 1.0, "Analysis complete.")

        return result
