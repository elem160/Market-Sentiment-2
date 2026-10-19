import hashlib
import time
import uuid
from typing import Callable, Awaitable
from sqlalchemy.orm import Session

from app.config import settings
from app.core.models import (
    Asset,
    AnalysisResult,
    PipelineMetrics,
    ScoredArticle,
    PipelineRationale,
)
from app.core.enums import PipelineStage, PipelineMode, CacheStatus, DecisionVerdict
from app.core.session_window import compute_session_window, compute_session_bucket
from app.core.exceptions import FreshnessViolationException, NewsUnavailableException
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
        resolved_asset: Asset | None = None,
    ) -> AnalysisResult:
        """
        Executes the 6-stage analysis pipeline with live progress reporting:
        Stage 1: Ticker Resolution & Session Window
        Stage 2: News Ingestion & Provider Health Validation
        Stage 2.5: Freshness Window Filtering (Core Invariant Enforcement)
        Stage 3: Deduplication & Relevance Filtering
        Stage 4: Local FinBERT Classification (512 tokens)
        Stage 5: LLM Catalyst Verification
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
        asset = resolved_asset or TickerService.validate_and_resolve(ticker)
        session = compute_session_window()
        stage_latencies["resolving_ticker"] = round((time.time() - t0) * 1000, 1)

        # Multi-dimensional cache key calculation (F-03)
        session_bucket, bucket_seconds = compute_session_bucket(session)
        provider_hash = "yfinance_finnhub_rss"
        cache_key = cls.compute_cache_key(asset.ticker, session_bucket, provider_hash, enable_llm)

        # Check Cache
        if not force_refresh:
            cached_result = SentimentRepository.get_cached_run(db, cache_key, max_age_seconds=bucket_seconds)
            if cached_result:
                logger.info(f"Cache hit for ticker {asset.ticker} (Key: {cache_key[:12]}...)")
                if on_progress:
                    await on_progress(PipelineStage.DONE, 1.0, "Loaded from cache.")
                return cached_result

        # ---------------------------------------------------------------------
        # Stage 2: News Ingestion & Provider Health Validation (F-04)
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

        # Total outage check (F-04): If every provider failed, raise 503 and do not cache
        if provider_outcomes and all(outcome.get("status") == "FAILED" for outcome in provider_outcomes.values()):
            logger.error(f"All external news providers failed for {asset.ticker}.")
            raise NewsUnavailableException("All external news providers failed to respond.")

        # ---------------------------------------------------------------------
        # Stage 2.5: Freshness Filtering (F-01 / F-07 Core Invariant)
        # ---------------------------------------------------------------------
        in_window_articles, freshness_excluded, excluded_out_of_window, excluded_missing_ts = (
            DeduplicationService.filter_by_session_window(raw_articles, session)
        )

        # If zero in-window articles survive, return NO_FRESH_NEWS cleanly
        if len(in_window_articles) == 0:
            summary = (
                f"No articles published inside the current session window "
                f"({excluded_out_of_window} out of window, {excluded_missing_ts} undated)."
            )
            rationale = PipelineRationale(
                summary=summary,
                observed_facts=[],
                inferences=[
                    f"Session window: {session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
                    f"Excluded {excluded_out_of_window} article(s) published outside session window.",
                    f"Excluded {excluded_missing_ts} article(s) with missing or untrusted timestamps.",
                ],
            )
            metrics = PipelineMetrics(
                total_sources=len(provider_outcomes),
                distinct_publishers=0,
                distinct_clusters=0,
                articles_ingested=len(raw_articles),
                articles_retained=0,
                articles_deduplicated=len(freshness_excluded),
                articles_scored_local=0,
                articles_sent_to_llm=0,
                excluded_out_of_window=excluded_out_of_window,
                excluded_missing_timestamp=excluded_missing_ts,
                total_latency_ms=round((time.time() - t_start) * 1000, 1),
                stage_latencies=stage_latencies,
            )

            sample_excluded_articles: list[ScoredArticle] = []
            for excl_art, reason, note in freshness_excluded:
                canonical_pub = DeduplicationService.normalize_publisher(excl_art.source_name)
                lead_text = f"{excl_art.title}. {excl_art.summary}".strip()[:500]
                sample_excluded_articles.append(
                    ScoredArticle(
                        article_id=excl_art.article_id,
                        provider=excl_art.provider,
                        source_name=excl_art.source_name,
                        canonical_publisher=canonical_pub,
                        canonical_url=excl_art.canonical_url,
                        title=excl_art.title,
                        published_at_utc=excl_art.published_at_utc,
                        lead_text=lead_text,
                        finbert_positive=0.0,
                        finbert_negative=0.0,
                        finbert_neutral=1.0,
                        finbert_directional_score=0.0,
                        finbert_confidence=0.0,
                        is_llm_catalyst=False,
                        catalyst_category=None,
                        exclusion_reason=reason,
                        final_weight=0.0,
                        effective_weight=0.0,
                        age_hours=0.0,
                        cluster_id="",
                    )
                )

            no_news_result = AnalysisResult(
                run_id=str(uuid.uuid4()),
                ticker=asset.ticker,
                company_name=asset.company_name,
                asset_type=asset.asset_type,
                session=session,
                decision=DecisionVerdict.HOLD,
                decision_confidence=0.0,
                sentiment_score=0.0,
                evidence_quality=0.0,
                disclaimer="Research & Market Sentiment Tool. Not Financial or Investment Advice.",
                rationale=rationale,
                metrics=metrics,
                articles=sample_excluded_articles,
                warnings=[summary],
                pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY,
                cache_status=CacheStatus.MISS,
                data_status="NO_FRESH_NEWS",
                llm_summary=None,
                model_versions={"finbert": settings.FINBERT_MODEL_NAME, "llm": "NONE"},
                config_version=settings.get_config_hash(),
            )

            # Cache NO_FRESH_NEWS result for min(bucket length, 5 minutes)
            SentimentRepository.save_analysis_run(db, no_news_result, cache_key, provider_outcomes)

            if on_progress:
                await on_progress(PipelineStage.DONE, 1.0, "Analysis complete (No fresh news).")
            return no_news_result

        # ---------------------------------------------------------------------
        # Stage 3: Deduplication, URL Cleaning & Relevance Filtering
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.FILTERING_DEDUPLICATING, 0.55, f"Deduplicating {len(in_window_articles)} articles and filtering relevance...")

        t2 = time.time()
        retained_articles, dedup_excluded, cluster_map = DeduplicationService.process_and_deduplicate(
            in_window_articles, asset.ticker, asset.company_name
        )
        stage_latencies["filtering_deduplicating"] = round((time.time() - t2) * 1000, 1)

        excluded_articles = freshness_excluded + dedup_excluded

        # ---------------------------------------------------------------------
        # Core Invariant Assertion (Immediately before FinBERT & Aggregation)
        # ---------------------------------------------------------------------
        for art in retained_articles:
            if art.published_at_utc is None or not session.is_timestamp_in_window(art.published_at_utc):
                ts_str = art.published_at_utc.isoformat() if art.published_at_utc else "None"
                raise FreshnessViolationException(
                    article_id=art.article_id,
                    timestamp_str=ts_str,
                    window_start=session.window_start_utc.isoformat(),
                    window_end=session.window_end_utc.isoformat(),
                )

        # ---------------------------------------------------------------------
        # Stage 4: Local FinBERT Sentiment Classification
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.FINBERT_SCORING, 0.70, f"Running local FinBERT inference on {len(retained_articles)} candidate articles...")

        t3 = time.time()
        finbert_service = FinBERTService.get_instance()
        scored_retained = await finbert_service.score_articles_async(retained_articles, cluster_map)
        stage_latencies["finbert_scoring"] = round((time.time() - t3) * 1000, 1)

        # Ensure lead_text is clean original text and not tokenizer round-trip (F-17)
        for scored_art in scored_retained:
            original_art = next((a for a in retained_articles if a.article_id == scored_art.article_id), None)
            if original_art:
                scored_art.lead_text = f"{original_art.title}. {original_art.summary}".strip()[:500]

        # Build complete article evidence list (retained + sample excluded)
        complete_article_list: list[ScoredArticle] = list(scored_retained)
        for excl_art, reason, note in excluded_articles:
            canonical_pub = DeduplicationService.normalize_publisher(excl_art.source_name)
            lead_text = f"{excl_art.title}. {excl_art.summary}".strip()[:500]
            complete_article_list.append(
                ScoredArticle(
                    article_id=excl_art.article_id,
                    provider=excl_art.provider,
                    source_name=excl_art.source_name,
                    canonical_publisher=canonical_pub,
                    canonical_url=excl_art.canonical_url,
                    title=excl_art.title,
                    published_at_utc=excl_art.published_at_utc,
                    lead_text=lead_text,
                    finbert_positive=0.0,
                    finbert_negative=0.0,
                    finbert_neutral=1.0,
                    finbert_directional_score=0.0,
                    finbert_confidence=0.0,
                    is_llm_catalyst=False,
                    catalyst_category=None,
                    exclusion_reason=reason,
                    final_weight=0.0,
                    effective_weight=0.0,
                    age_hours=0.0,
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
            llm_summary=llm_summary,
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
            excluded_out_of_window=excluded_out_of_window,
            excluded_missing_timestamp=excluded_missing_ts,
            prompt_tokens=llm_telemetry.get("prompt_tokens", 0),
            completion_tokens=llm_telemetry.get("completion_tokens", 0),
            estimated_cost_usd=llm_telemetry.get("estimated_cost_usd", 0.0),
            total_latency_ms=total_latency_ms,
            stage_latencies=stage_latencies,
        )

        run_id = str(uuid.uuid4())
        used_llm_model = llm_telemetry.get("model") or settings.LLM_MODEL_ID
        model_versions = {
            "finbert": settings.FINBERT_MODEL_NAME,
            "llm": used_llm_model if pipeline_mode == PipelineMode.HYBRID_FINBERT_LLM else "NONE",
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
            data_status="OK",
            llm_summary=llm_summary or None,
            model_versions=model_versions,
            config_version=settings.get_config_hash(),
        )

        # Persist run and evidence in database
        SentimentRepository.save_analysis_run(db, result, cache_key, provider_outcomes)

        if on_progress:
            await on_progress(PipelineStage.DONE, 1.0, "Analysis complete.")

        return result
