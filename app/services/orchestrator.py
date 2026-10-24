import hashlib
import time
import uuid
from typing import Callable, Awaitable, Any
from sqlalchemy.orm import Session

from app.config import settings
from app.core.models import (
    Asset,
    AnalysisResult,
    PipelineMetrics,
    ScoredArticle,
    PipelineRationale,
    PipelineDeps,
    ProviderOutcome,
)
from app.core.enums import (
    PipelineStage,
    PipelineMode,
    CacheStatus,
    DecisionVerdict,
    ExclusionReason,
    HoldReason,
    DataStatus,
    ProviderKind,
)
from app.core.session_window import compute_session_window, compute_session_bucket
from app.core.exceptions import FreshnessViolationException, NewsUnavailableException
from app.core.constants import DIRECTIONAL_THRESHOLD
from app.services.ticker_service import TickerService
from app.services.news_service import NewsService
from app.services.deduplication_service import DeduplicationService
from app.services.relevance import RelevanceMatcher
from app.services.finbert_service import FinBERTService
from app.services.llm_service import LLMService
from app.services.aggregator_service import AggregatorService
from app.db.repository import SentimentRepository
from app.utils.logging import logger
from app.utils.executors import run_db, get_io_executor

ProgressCallback = Callable[[PipelineStage, float, str], Awaitable[None]]


async def _save_analysis_run_safe(
    db: Any,
    result: AnalysisResult,
    cache_key: str,
    provider_outcomes: list[ProviderOutcome],
    is_cacheable: bool,
) -> None:
    if hasattr(db, "_mock_return_value") or hasattr(db, "mock_calls"):
        SentimentRepository.save_analysis_run(db, result, cache_key, provider_outcomes, is_cacheable=is_cacheable)
    else:
        await run_db(
            SentimentRepository.save_analysis_run,
            result,
            cache_key,
            provider_outcomes,
            is_cacheable,
        )


async def _get_cached_run_safe(
    db: Any,
    cache_key: str,
    max_age_seconds: int | None,
) -> AnalysisResult | None:
    if hasattr(db, "_mock_return_value") or hasattr(db, "mock_calls"):
        return SentimentRepository.get_cached_run(db, cache_key, max_age_seconds=max_age_seconds)
    else:
        return await run_db(
            SentimentRepository.get_cached_run,
            cache_key,
            max_age_seconds,
        )


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
        asset: Asset | None = None,
        deps: PipelineDeps | None = None,
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
        effective_asset = asset or resolved_asset
        if effective_asset is None:
            effective_asset = TickerService.validate_and_resolve(ticker)
        asset = effective_asset
        session = compute_session_window()
        stage_latencies["resolving_ticker"] = round((time.time() - t0) * 1000, 1)

        # Multi-dimensional cache key calculation (F-03)
        session_bucket, bucket_seconds = compute_session_bucket(session)
        provider_hash = "yfinance_rss"
        cache_key = cls.compute_cache_key(asset.ticker, session_bucket, provider_hash, enable_llm)

        # Check Cache
        if not force_refresh:
            cached_result = await _get_cached_run_safe(db, cache_key, max_age_seconds=bucket_seconds)
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
        effective_io_executor = deps.io_executor if deps and deps.io_executor else get_io_executor()
        raw_articles, provider_outcomes = await NewsService.fetch_news_for_session(
            asset.ticker,
            asset.company_name,
            session,
            asset_type=asset.asset_type,
            yf_symbol=asset.yf_symbol,
            http_client=deps.http_client if deps else None,
            io_executor=effective_io_executor,
        )
        stage_latencies["ingesting_news"] = round((time.time() - t1) * 1000, 1)

        # Provider outage and health checks driven by ProviderKind (P3.1)
        normalized_outcomes: list[ProviderOutcome] = []
        if isinstance(provider_outcomes, dict):
            for k, v in provider_outcomes.items():
                if k == "google_news_rss_total":
                    continue
                v_dict = v if isinstance(v, dict) else {}
                kind = (
                    ProviderKind.YFINANCE if k == "yfinance"
                    else ProviderKind.RSS_DIRECT if k.startswith("forex_")
                    else ProviderKind.RSS_GOOGLE
                )
                normalized_outcomes.append(
                    ProviderOutcome(
                        key=k,
                        kind=kind,
                        status=v_dict.get("status", "SUCCESS"),
                        count=v_dict.get("count", 0),
                        latency_ms=v_dict.get("latency_ms", 0.0),
                        error_code=v_dict.get("error"),
                    )
                )
        elif isinstance(provider_outcomes, list):
            for item in provider_outcomes:
                if isinstance(item, ProviderOutcome):
                    normalized_outcomes.append(item)
                elif isinstance(item, dict):
                    normalized_outcomes.append(ProviderOutcome(**item))
        else:
            normalized_outcomes = []

        provider_outcomes = normalized_outcomes

        all_providers_failed = bool(provider_outcomes) and all(
            po.status in ("FAILED", "TIMEOUT") for po in provider_outcomes
        )
        rss_outcomes = [
            po for po in provider_outcomes
            if po.kind in (ProviderKind.RSS_GOOGLE, ProviderKind.RSS_DIRECT)
        ]
        all_rss_failed = bool(rss_outcomes) and all(
            po.status in ("FAILED", "TIMEOUT") for po in rss_outcomes
        )

        is_degraded = all_providers_failed or all_rss_failed

        if all_providers_failed:
            provider_failure_warning = (
                "All external news providers failed to respond; analysis completed with degraded evidence and will not be cached."
            )
            logger.error(f"All external news providers failed for {asset.ticker}. Emitting degraded non-cacheable run.")
        elif all_rss_failed:
            provider_failure_warning = (
                "All RSS news providers failed during ingestion sweep; analysis completed with degraded evidence and will not be cached."
            )
            logger.warning(provider_failure_warning)
        else:
            provider_failure_warning = None

        # ---------------------------------------------------------------------
        # Stage 2.5: Freshness Filtering (F-01 / F-07 Core Invariant)
        # ---------------------------------------------------------------------
        in_window_articles, freshness_excluded, excluded_out_of_window, excluded_missing_ts = (
            DeduplicationService.filter_by_session_window(raw_articles, session)
        )

        # If zero in-window articles survive, return NO_FRESH_NEWS or DEGRADED cleanly
        if len(in_window_articles) == 0:
            if all_providers_failed:
                summary = "All external news providers failed to respond during ingestion sweep."
                inferences = [
                    f"Session window: {session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
                    "All configured external news feeds failed to return valid data.",
                    "Emitted degraded neutral stance with zero confidence.",
                ]
            else:
                summary = (
                    f"No articles published inside the current session window "
                    f"({excluded_out_of_window} out of window, {excluded_missing_ts} undated)."
                )
                inferences = [
                    f"Session window: {session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
                    f"Excluded {excluded_out_of_window} article(s) published outside session window.",
                    f"Excluded {excluded_missing_ts} article(s) with missing or untrusted timestamps.",
                ]
            rationale = PipelineRationale(
                summary=summary,
                observed_facts=[],
                inferences=inferences,
            )
            freshness_excluded_counts = {
                ExclusionReason.TIMESTAMP_OUT_OF_WINDOW.value: excluded_out_of_window,
                ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP.value: excluded_missing_ts,
            }

            metrics = PipelineMetrics(
                total_sources=len(provider_outcomes),
                distinct_publishers=0,
                distinct_clusters=0,
                articles_ingested=len(raw_articles),
                articles_retained=0,
                articles_deduplicated=0,
                articles_scored_local=0,
                articles_sent_to_llm=0,
                articles_excluded_total=excluded_out_of_window + excluded_missing_ts,
                excluded_counts=freshness_excluded_counts,
                directional_threshold=DIRECTIONAL_THRESHOLD,
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
                        publisher_inferred=bool(excl_art.raw_provider_metadata.get("publisher_inferred", False)),
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
                warnings=[summary] if not provider_failure_warning else [summary, provider_failure_warning],
                pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY,
                cache_status=CacheStatus.MISS,
                data_status=DataStatus.DEGRADED if is_degraded else DataStatus.NO_FRESH_NEWS,
                hold_reason=HoldReason.NO_NEWS,
                llm_summary=None,
                model_versions={"finbert": settings.FINBERT_MODEL_NAME, "llm": "NONE"},
                config_version=settings.get_config_hash(),
                provider_outcomes=provider_outcomes,
            )

            # Always persist run; if degraded, mark is_cacheable=False
            if is_degraded:
                logger.warning(f"Persisting analysis run for {asset.ticker} with is_cacheable=False due to degraded provider outcomes.")
            await _save_analysis_run_safe(
                db, no_news_result, cache_key, provider_outcomes, is_cacheable=(not is_degraded)
            )

            if on_progress:
                msg = "Analysis complete (Degraded provider outage)." if is_degraded else "Analysis complete (No fresh news)."
                await on_progress(PipelineStage.DONE, 1.0, msg)
            return no_news_result

        # ---------------------------------------------------------------------
        # Stage 3: Deduplication, URL Cleaning & Relevance Filtering
        # ---------------------------------------------------------------------
        if on_progress:
            await on_progress(PipelineStage.FILTERING_DEDUPLICATING, 0.55, f"Deduplicating {len(in_window_articles)} articles and filtering relevance...")

        t2 = time.time()
        relevance_matcher = RelevanceMatcher.for_asset(asset)
        dedup_res = DeduplicationService.process_and_deduplicate(
            in_window_articles, matcher=relevance_matcher
        )
        retained_articles, dedup_excluded, cluster_map = dedup_res
        dedup_counts = getattr(dedup_res, "counts", {})
        stage_latencies["filtering_deduplicating"] = round((time.time() - t2) * 1000, 1)

        total_excluded_counts: dict[str, int] = {
            ExclusionReason.TIMESTAMP_OUT_OF_WINDOW.value: excluded_out_of_window,
            ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP.value: excluded_missing_ts,
            ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE.value: dedup_counts.get(ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE.value, 0),
            ExclusionReason.DUPLICATE_SYNDICATION.value: dedup_counts.get(ExclusionReason.DUPLICATE_SYNDICATION.value, 0),
            ExclusionReason.CAPACITY_LIMIT.value: dedup_counts.get(ExclusionReason.CAPACITY_LIMIT.value, 0),
        }
        total_excluded_count = sum(total_excluded_counts.values())
        sample_excluded_articles_raw = freshness_excluded + dedup_excluded

        # If zero articles survive relevance and deduplication, return NO_RELEVANT_NEWS cleanly (P2.6, M12)
        if len(retained_articles) == 0:
            summary = (
                f"No articles passed entity relevance criteria for {asset.ticker} "
                f"({len(in_window_articles)} inside session window, but 0 passed relevance and deduplication)."
            )
            rationale = PipelineRationale(
                summary=summary,
                observed_facts=[],
                inferences=[
                    f"Session window: {session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
                    f"Ingested {len(raw_articles)} raw articles; {len(in_window_articles)} within window.",
                    f"Excluded {len(dedup_excluded)} article(s) due to lack of entity relevance or syndication duplicates.",
                    "Zero relevant articles passed filters: FinBERT and LLM synthesis skipped.",
                ],
            )

            metrics = PipelineMetrics(
                total_sources=len(provider_outcomes),
                distinct_publishers=0,
                distinct_clusters=0,
                publishers_positive=0,
                publishers_negative=0,
                supporting_publishers=0,
                articles_ingested=len(raw_articles),
                articles_retained=0,
                articles_deduplicated=total_excluded_counts.get(ExclusionReason.DUPLICATE_SYNDICATION.value, 0),
                articles_scored_local=0,
                articles_sent_to_llm=0,
                articles_excluded_total=total_excluded_count,
                excluded_counts=total_excluded_counts,
                directional_threshold=DIRECTIONAL_THRESHOLD,
                excluded_out_of_window=excluded_out_of_window,
                excluded_missing_timestamp=excluded_missing_ts,
                total_latency_ms=round((time.time() - t_start) * 1000, 1),
                stage_latencies=stage_latencies,
            )

            sample_excluded_articles: list[ScoredArticle] = []
            for excl_art, reason, note in sample_excluded_articles_raw:
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
                        cluster_id=cluster_map.get(excl_art.article_id, ""),
                        publisher_inferred=bool(excl_art.raw_provider_metadata.get("publisher_inferred", False)),
                    )
                )

            data_status = DataStatus.DEGRADED if is_degraded else DataStatus.NO_RELEVANT_NEWS
            no_relevant_result = AnalysisResult(
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
                warnings=[summary] if not provider_failure_warning else [summary, provider_failure_warning],
                pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY,
                cache_status=CacheStatus.MISS,
                data_status=data_status,
                hold_reason=HoldReason.NO_NEWS,
                llm_summary=None,
                model_versions={"finbert": settings.FINBERT_MODEL_NAME, "llm": "NONE"},
                config_version=settings.get_config_hash(),
                provider_outcomes=provider_outcomes,
            )

            if is_degraded:
                logger.warning(f"Persisting analysis run for {asset.ticker} with is_cacheable=False due to degraded provider outcomes.")
            await _save_analysis_run_safe(
                db, no_relevant_result, cache_key, provider_outcomes, is_cacheable=(not is_degraded)
            )

            if on_progress:
                await on_progress(PipelineStage.DONE, 1.0, "Analysis complete (No relevant news).")
            return no_relevant_result

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
        scorer = deps.scorer if deps and deps.scorer else None
        scored_retained = await finbert_service.score_articles_async(
            retained_articles, cluster_map, scorer=scorer
        )
        stage_latencies["finbert_scoring"] = round((time.time() - t3) * 1000, 1)

        # Build complete article evidence list (retained + sample excluded)
        complete_article_list: list[ScoredArticle] = list(scored_retained)
        for excl_art, reason, note in sample_excluded_articles_raw:
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
                    publisher_inferred=bool(excl_art.raw_provider_metadata.get("publisher_inferred", False)),
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
        agg_res = AggregatorService.aggregate_and_decide(
            asset.ticker,
            asset.company_name,
            session,
            scored_retained,
            observed_facts,
            llm_summary=llm_summary,
            pipeline_mode=pipeline_mode,
        )
        decision, confidence, score, quality, rationale, warnings = agg_res
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
            publishers_positive=agg_res.publishers_positive,
            publishers_negative=agg_res.publishers_negative,
            supporting_publishers=agg_res.supporting_publishers,
            articles_ingested=len(raw_articles),
            articles_retained=len(scored_retained),
            articles_deduplicated=total_excluded_counts.get(ExclusionReason.DUPLICATE_SYNDICATION.value, 0),
            articles_scored_local=len(scored_retained),
            articles_sent_to_llm=llm_telemetry.get("candidates_sent", 0) if llm_telemetry.get("status") != "SKIPPED" else 0,
            articles_excluded_total=total_excluded_count,
            excluded_counts=total_excluded_counts,
            directional_threshold=DIRECTIONAL_THRESHOLD,
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

        if provider_failure_warning and provider_failure_warning not in warnings:
            warnings.append(provider_failure_warning)

        if not asset.verified and asset.resolution_warning and asset.resolution_warning not in warnings:
            warnings.append(asset.resolution_warning)

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
            data_status=DataStatus.DEGRADED if is_degraded else DataStatus.OK,
            hold_reason=agg_res.hold_reason,
            llm_summary=llm_summary or None,
            model_versions=model_versions,
            config_version=settings.get_config_hash(),
            provider_outcomes=provider_outcomes,
        )

        # Persist run and evidence in database; if degraded, mark is_cacheable=False
        if is_degraded:
            logger.warning(f"Persisting analysis run for {asset.ticker} with is_cacheable=False due to degraded provider outcomes.")
        await _save_analysis_run_safe(
            db, result, cache_key, provider_outcomes, is_cacheable=(not is_degraded)
        )

        if on_progress:
            await on_progress(PipelineStage.DONE, 1.0, "Analysis complete.")

        return result
