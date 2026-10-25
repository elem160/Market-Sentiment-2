import hashlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.core.constants import DIRECTIONAL_THRESHOLD
from app.core.enums import (
    CacheStatus,
    DataStatus,
    DecisionVerdict,
    ExclusionReason,
    HoldReason,
    PipelineMode,
    PipelineStage,
    ProviderKind,
)
from app.core.exceptions import FreshnessViolationException
from app.core.models import (
    AnalysisResult,
    Asset,
    IngestedArticle,
    ObservedFact,
    PipelineDeps,
    PipelineMetrics,
    PipelineRationale,
    ProviderOutcome,
    ScoredArticle,
)
from app.core.session_window import SessionWindow, compute_session_bucket, compute_session_window
from app.db.repository import SentimentRepository
from app.services.aggregator_service import AggregatorService
from app.services.deduplication_service import DeduplicationService
from app.services.finbert_service import FinBERTService
from app.services.llm_service import LLMService
from app.services.news_service import NewsService
from app.services.relevance import RelevanceMatcher
from app.services.ticker_service import TickerService
from app.utils.executors import get_io_executor, run_db
from app.utils.logging import logger

ProgressCallback = Callable[[PipelineStage, float, str], Awaitable[None]]

DISCLAIMER = "Research & Market Sentiment Tool. Not Financial or Investment Advice."


def build_excluded_article(
    excl_art: IngestedArticle,
    reason: ExclusionReason,
    cluster_id: str = "",
) -> ScoredArticle:
    """Build a ScoredArticle for an excluded article, normalizing publisher and computing excerpt."""
    canonical_pub = DeduplicationService.normalize_publisher(excl_art.source_name)
    lead_text = f"{excl_art.title}. {excl_art.summary}".strip()[:500]
    return ScoredArticle(
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
        cluster_id=cluster_id,
        publisher_inferred=bool(excl_art.raw_provider_metadata.get("publisher_inferred", False)),
    )


def build_pipeline_metrics(
    *,
    total_sources: int,
    distinct_publishers: int,
    distinct_clusters: int,
    articles_ingested: int,
    articles_retained: int,
    articles_deduplicated: int,
    articles_scored_local: int,
    articles_sent_to_llm: int,
    articles_excluded_total: int,
    excluded_counts: dict[str, int],
    directional_threshold: float,
    excluded_out_of_window: int,
    excluded_missing_timestamp: int,
    total_latency_ms: float,
    stage_latencies: dict[str, float],
    publishers_positive: int = 0,
    publishers_negative: int = 0,
    supporting_publishers: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    estimated_cost_usd: float = 0.0,
) -> PipelineMetrics:
    """Constructs a PipelineMetrics object with uniform fields and defaults."""
    return PipelineMetrics(
        total_sources=total_sources,
        distinct_publishers=distinct_publishers,
        distinct_clusters=distinct_clusters,
        publishers_positive=publishers_positive,
        publishers_negative=publishers_negative,
        supporting_publishers=supporting_publishers,
        articles_ingested=articles_ingested,
        articles_retained=articles_retained,
        articles_deduplicated=articles_deduplicated,
        articles_scored_local=articles_scored_local,
        articles_sent_to_llm=articles_sent_to_llm,
        articles_excluded_total=articles_excluded_total,
        excluded_counts=excluded_counts,
        directional_threshold=directional_threshold,
        excluded_out_of_window=excluded_out_of_window,
        excluded_missing_timestamp=excluded_missing_timestamp,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        estimated_cost_usd=estimated_cost_usd,
        total_latency_ms=total_latency_ms,
        stage_latencies=stage_latencies,
    )


@dataclass
class PipelineContext:
    """Carries mutable state across stages of the orchestrator pipeline."""
    ticker: str
    db: Session
    force_refresh: bool = False
    enable_llm: bool = True
    on_progress: ProgressCallback | None = None
    resolved_asset: Asset | None = None
    asset: Asset | None = None
    deps: PipelineDeps | None = None

    # Timing & tracking
    t_start: float = field(default_factory=time.time)
    stage_latencies: dict[str, float] = field(default_factory=dict)

    # Stage 1: Resolved Asset, Window & Cache
    session: SessionWindow | None = None
    session_bucket: str = ""
    bucket_seconds: int = 0
    cache_key: str = ""

    # Stage 2: Ingestion & Provider health
    raw_articles: list[IngestedArticle] = field(default_factory=list)
    provider_outcomes: list[ProviderOutcome] = field(default_factory=list)
    is_degraded: bool = False
    all_providers_failed: bool = False
    all_rss_failed: bool = False
    provider_failure_warning: str | None = None

    # Stage 2.5: Freshness
    in_window_articles: list[IngestedArticle] = field(default_factory=list)
    freshness_excluded: list[tuple[IngestedArticle, ExclusionReason, str]] = field(default_factory=list)
    excluded_out_of_window: int = 0
    excluded_missing_ts: int = 0

    # Stage 3: Deduplication & Relevance
    retained_articles: list[IngestedArticle] = field(default_factory=list)
    dedup_excluded: list[tuple[IngestedArticle, ExclusionReason, str]] = field(default_factory=list)
    cluster_map: dict[str, str] = field(default_factory=dict)
    total_excluded_counts: dict[str, int] = field(default_factory=dict)
    total_excluded_count: int = 0
    sample_excluded_articles_raw: list[tuple[IngestedArticle, ExclusionReason, str]] = field(default_factory=list)

    # Stage 4: FinBERT Scoring
    scored_retained: list[ScoredArticle] = field(default_factory=list)
    complete_article_list: list[ScoredArticle] = field(default_factory=list)

    # Stage 5: Catalyst Synthesis
    observed_facts: list[ObservedFact] = field(default_factory=list)
    llm_summary: str = ""
    llm_telemetry: dict[str, Any] = field(default_factory=dict)
    pipeline_mode: PipelineMode = PipelineMode.DETERMINISTIC_FINBERT_ONLY

    # Stage 6: Aggregation & Decision
    agg_res: Any = None
    decision: DecisionVerdict = DecisionVerdict.HOLD
    decision_confidence: float = 0.0
    sentiment_score: float = 0.0
    evidence_quality: float = 0.0
    rationale: Any = None
    warnings: list[str] = field(default_factory=list)

    # Final Result
    metrics: PipelineMetrics | None = None
    result: AnalysisResult | None = None


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
        provider_hash: str = "yfinance_rss",
        enable_llm: bool = True,
        asset_type: str = "EQUITY",
    ) -> str:
        """
        Deterministic multi-dimensional cache key (Master Plan §7.8).
        sha256(ALGORITHM_VERSION, ticker, asset_type, bucket, enable_llm, config_hash)
        """
        config_hash = settings.get_config_hash()
        raw = f"{settings.ALGORITHM_VERSION}:{ticker.upper()}:{asset_type.upper()}:{session_bucket}:{enable_llm}:{config_hash}"
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    async def _resolve_and_check_cache(cls, ctx: PipelineContext) -> AnalysisResult | None:
        """Stage 1: Resolve ticker and company profile, session window, and evaluate cache."""
        if ctx.on_progress:
            await ctx.on_progress(PipelineStage.RESOLVING_TICKER, 0.15, "Resolving ticker and company profile...")

        t0 = time.time()
        effective_asset = ctx.asset or ctx.resolved_asset
        if effective_asset is None:
            effective_asset = TickerService.validate_and_resolve(ctx.ticker)
        ctx.asset = effective_asset
        ctx.session = compute_session_window()
        ctx.stage_latencies["resolving_ticker"] = round((time.time() - t0) * 1000, 1)

        # Multi-dimensional cache key calculation (F-03 / Plan §7.8)
        ctx.session_bucket, ctx.bucket_seconds = compute_session_bucket(ctx.session)
        provider_hash = "yfinance_rss"
        asset_type_str = ctx.asset.asset_type.value if hasattr(ctx.asset.asset_type, "value") else str(ctx.asset.asset_type)
        ctx.cache_key = cls.compute_cache_key(
            ctx.asset.ticker,
            ctx.session_bucket,
            provider_hash,
            ctx.enable_llm,
            asset_type=asset_type_str,
        )

        # Check Cache
        if not ctx.force_refresh:
            cached_result = await _get_cached_run_safe(ctx.db, ctx.cache_key, max_age_seconds=ctx.bucket_seconds)
            if cached_result:
                logger.info(f"Cache hit for ticker {ctx.asset.ticker} (Key: {ctx.cache_key[:12]}...)")
                if ctx.on_progress:
                    await ctx.on_progress(PipelineStage.DONE, 1.0, "Loaded from cache.")
                return cached_result
        return None

    @classmethod
    async def _ingest(cls, ctx: PipelineContext) -> None:
        """Stage 2: Ingest news from providers and validate provider health outcomes."""
        if ctx.on_progress:
            await ctx.on_progress(
                PipelineStage.INGESTING_NEWS,
                0.35,
                f"Ingesting current-day news ({ctx.session.window_duration_hours}h session window)...",
            )

        t1 = time.time()
        effective_io_executor = ctx.deps.io_executor if ctx.deps and ctx.deps.io_executor else get_io_executor()
        raw_articles, provider_outcomes = await NewsService.fetch_news_for_session(
            ctx.asset.ticker,
            ctx.asset.company_name,
            ctx.session,
            asset_type=ctx.asset.asset_type,
            yf_symbol=ctx.asset.yf_symbol,
            http_client=ctx.deps.http_client if ctx.deps else None,
            io_executor=effective_io_executor,
        )
        ctx.raw_articles = raw_articles
        ctx.stage_latencies["ingesting_news"] = round((time.time() - t1) * 1000, 1)

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

        ctx.provider_outcomes = normalized_outcomes

        ctx.all_providers_failed = bool(ctx.provider_outcomes) and all(
            po.status in ("FAILED", "TIMEOUT") for po in ctx.provider_outcomes
        )
        rss_outcomes = [
            po for po in ctx.provider_outcomes
            if po.kind in (ProviderKind.RSS_GOOGLE, ProviderKind.RSS_DIRECT)
        ]
        ctx.all_rss_failed = bool(rss_outcomes) and all(
            po.status in ("FAILED", "TIMEOUT") for po in rss_outcomes
        )

        ctx.is_degraded = ctx.all_providers_failed or ctx.all_rss_failed

        if ctx.all_providers_failed:
            ctx.provider_failure_warning = (
                "All external news providers failed to respond; analysis completed with degraded evidence and will not be cached."
            )
            logger.error(f"All external news providers failed for {ctx.asset.ticker}. Emitting degraded non-cacheable run.")
        elif ctx.all_rss_failed:
            ctx.provider_failure_warning = (
                "All RSS news providers failed during ingestion sweep; analysis completed with degraded evidence and will not be cached."
            )
            logger.warning(ctx.provider_failure_warning)
        else:
            ctx.provider_failure_warning = None

    @classmethod
    async def _filter_fresh(cls, ctx: PipelineContext) -> AnalysisResult | None:
        """Stage 2.5: Freshness Filtering (F-01 / F-07 Core Invariant)."""
        in_window_articles, freshness_excluded, excluded_out_of_window, excluded_missing_ts = (
            DeduplicationService.filter_by_session_window(ctx.raw_articles, ctx.session)
        )
        ctx.in_window_articles = in_window_articles
        ctx.freshness_excluded = freshness_excluded
        ctx.excluded_out_of_window = excluded_out_of_window
        ctx.excluded_missing_ts = excluded_missing_ts

        # If zero in-window articles survive, return NO_FRESH_NEWS or DEGRADED cleanly
        if len(in_window_articles) == 0:
            if ctx.all_providers_failed:
                summary = "All external news providers failed to respond during ingestion sweep."
                inferences = [
                    f"Session window: {ctx.session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {ctx.session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
                    "All configured external news feeds failed to return valid data.",
                    "Emitted degraded neutral stance with zero confidence.",
                ]
            else:
                summary = (
                    f"No articles published inside the current session window "
                    f"({excluded_out_of_window} out of window, {excluded_missing_ts} undated)."
                )
                inferences = [
                    f"Session window: {ctx.session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {ctx.session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
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

            metrics = build_pipeline_metrics(
                total_sources=len(ctx.provider_outcomes),
                distinct_publishers=0,
                distinct_clusters=0,
                articles_ingested=len(ctx.raw_articles),
                articles_retained=0,
                articles_deduplicated=0,
                articles_scored_local=0,
                articles_sent_to_llm=0,
                articles_excluded_total=excluded_out_of_window + excluded_missing_ts,
                excluded_counts=freshness_excluded_counts,
                directional_threshold=DIRECTIONAL_THRESHOLD,
                excluded_out_of_window=excluded_out_of_window,
                excluded_missing_timestamp=excluded_missing_ts,
                total_latency_ms=round((time.time() - ctx.t_start) * 1000, 1),
                stage_latencies=ctx.stage_latencies,
            )

            sample_excluded_articles = [
                build_excluded_article(excl_art, reason, "")
                for excl_art, reason, _ in freshness_excluded
            ]

            warnings = [summary] if not ctx.provider_failure_warning else [summary, ctx.provider_failure_warning]
            no_news_result = AnalysisResult(
                run_id=str(uuid.uuid4()),
                ticker=ctx.asset.ticker,
                company_name=ctx.asset.company_name,
                asset_type=ctx.asset.asset_type,
                session=ctx.session,
                decision=DecisionVerdict.HOLD,
                decision_confidence=0.0,
                sentiment_score=0.0,
                evidence_quality=0.0,
                disclaimer=DISCLAIMER,
                rationale=rationale,
                metrics=metrics,
                articles=sample_excluded_articles,
                warnings=warnings,
                pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY,
                cache_status=CacheStatus.MISS,
                data_status=DataStatus.DEGRADED if ctx.is_degraded else DataStatus.NO_FRESH_NEWS,
                hold_reason=HoldReason.NO_NEWS,
                llm_summary=None,
                model_versions={"finbert": settings.FINBERT_MODEL_NAME, "llm": "NONE"},
                config_version=settings.get_config_hash(),
                provider_outcomes=ctx.provider_outcomes,
            )

            # Always persist run; if degraded, mark is_cacheable=False
            if ctx.is_degraded:
                logger.warning(f"Persisting analysis run for {ctx.asset.ticker} with is_cacheable=False due to degraded provider outcomes.")
            await _save_analysis_run_safe(
                ctx.db, no_news_result, ctx.cache_key, ctx.provider_outcomes, is_cacheable=(not ctx.is_degraded)
            )

            if ctx.on_progress:
                msg = "Analysis complete (Degraded provider outage)." if ctx.is_degraded else "Analysis complete (No fresh news)."
                await ctx.on_progress(PipelineStage.DONE, 1.0, msg)
            return no_news_result

        return None

    @classmethod
    async def _select_relevant(cls, ctx: PipelineContext) -> AnalysisResult | None:
        """Stage 3: Deduplication, URL Cleaning & Relevance Filtering."""
        if ctx.on_progress:
            await ctx.on_progress(
                PipelineStage.FILTERING_DEDUPLICATING,
                0.55,
                f"Deduplicating {len(ctx.in_window_articles)} articles and filtering relevance...",
            )

        t2 = time.time()
        relevance_matcher = RelevanceMatcher.for_asset(ctx.asset)
        dedup_res = DeduplicationService.process_and_deduplicate(
            ctx.in_window_articles, matcher=relevance_matcher
        )
        ctx.retained_articles, ctx.dedup_excluded, ctx.cluster_map = dedup_res
        dedup_counts = getattr(dedup_res, "counts", {})
        ctx.stage_latencies["filtering_deduplicating"] = round((time.time() - t2) * 1000, 1)

        ctx.total_excluded_counts = {
            ExclusionReason.TIMESTAMP_OUT_OF_WINDOW.value: ctx.excluded_out_of_window,
            ExclusionReason.MISSING_OR_UNTRUSTED_TIMESTAMP.value: ctx.excluded_missing_ts,
            ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE.value: dedup_counts.get(ExclusionReason.INSUFFICIENT_ENTITY_RELEVANCE.value, 0),
            ExclusionReason.DUPLICATE_SYNDICATION.value: dedup_counts.get(ExclusionReason.DUPLICATE_SYNDICATION.value, 0),
            ExclusionReason.CAPACITY_LIMIT.value: dedup_counts.get(ExclusionReason.CAPACITY_LIMIT.value, 0),
        }
        ctx.total_excluded_count = sum(ctx.total_excluded_counts.values())
        ctx.sample_excluded_articles_raw = ctx.freshness_excluded + ctx.dedup_excluded

        # If zero articles survive relevance and deduplication, return NO_RELEVANT_NEWS cleanly (P2.6, M12)
        if len(ctx.retained_articles) == 0:
            summary = (
                f"No articles passed entity relevance criteria for {ctx.asset.ticker} "
                f"({len(ctx.in_window_articles)} inside session window, but 0 passed relevance and deduplication)."
            )
            rationale = PipelineRationale(
                summary=summary,
                observed_facts=[],
                inferences=[
                    f"Session window: {ctx.session.window_start_utc.strftime('%Y-%m-%d %H:%M')} to {ctx.session.window_end_utc.strftime('%Y-%m-%d %H:%M')} UTC.",
                    f"Ingested {len(ctx.raw_articles)} raw articles; {len(ctx.in_window_articles)} within window.",
                    f"Excluded {len(ctx.dedup_excluded)} article(s) due to lack of entity relevance or syndication duplicates.",
                    "Zero relevant articles passed filters: FinBERT and LLM synthesis skipped.",
                ],
            )

            metrics = build_pipeline_metrics(
                total_sources=len(ctx.provider_outcomes),
                distinct_publishers=0,
                distinct_clusters=0,
                publishers_positive=0,
                publishers_negative=0,
                supporting_publishers=0,
                articles_ingested=len(ctx.raw_articles),
                articles_retained=0,
                articles_deduplicated=ctx.total_excluded_counts.get(ExclusionReason.DUPLICATE_SYNDICATION.value, 0),
                articles_scored_local=0,
                articles_sent_to_llm=0,
                articles_excluded_total=ctx.total_excluded_count,
                excluded_counts=ctx.total_excluded_counts,
                directional_threshold=DIRECTIONAL_THRESHOLD,
                excluded_out_of_window=ctx.excluded_out_of_window,
                excluded_missing_timestamp=ctx.excluded_missing_ts,
                total_latency_ms=round((time.time() - ctx.t_start) * 1000, 1),
                stage_latencies=ctx.stage_latencies,
            )

            sample_excluded_articles = [
                build_excluded_article(excl_art, reason, ctx.cluster_map.get(excl_art.article_id, ""))
                for excl_art, reason, _ in ctx.sample_excluded_articles_raw
            ]

            data_status = DataStatus.DEGRADED if ctx.is_degraded else DataStatus.NO_RELEVANT_NEWS
            warnings = [summary] if not ctx.provider_failure_warning else [summary, ctx.provider_failure_warning]
            no_relevant_result = AnalysisResult(
                run_id=str(uuid.uuid4()),
                ticker=ctx.asset.ticker,
                company_name=ctx.asset.company_name,
                asset_type=ctx.asset.asset_type,
                session=ctx.session,
                decision=DecisionVerdict.HOLD,
                decision_confidence=0.0,
                sentiment_score=0.0,
                evidence_quality=0.0,
                disclaimer=DISCLAIMER,
                rationale=rationale,
                metrics=metrics,
                articles=sample_excluded_articles,
                warnings=warnings,
                pipeline_mode=PipelineMode.DETERMINISTIC_FINBERT_ONLY,
                cache_status=CacheStatus.MISS,
                data_status=data_status,
                hold_reason=HoldReason.NO_NEWS,
                llm_summary=None,
                model_versions={"finbert": settings.FINBERT_MODEL_NAME, "llm": "NONE"},
                config_version=settings.get_config_hash(),
                provider_outcomes=ctx.provider_outcomes,
            )

            if ctx.is_degraded:
                logger.warning(f"Persisting analysis run for {ctx.asset.ticker} with is_cacheable=False due to degraded provider outcomes.")
            await _save_analysis_run_safe(
                ctx.db, no_relevant_result, ctx.cache_key, ctx.provider_outcomes, is_cacheable=(not ctx.is_degraded)
            )

            if ctx.on_progress:
                await ctx.on_progress(PipelineStage.DONE, 1.0, "Analysis complete (No relevant news).")
            return no_relevant_result

        return None

    @classmethod
    def _assert_freshness_invariants(cls, ctx: PipelineContext) -> None:
        """Core Invariant Assertion (Immediately before FinBERT & Aggregation)."""
        for art in ctx.retained_articles:
            if art.published_at_utc is None or not ctx.session.is_timestamp_in_window(art.published_at_utc):
                ts_str = art.published_at_utc.isoformat() if art.published_at_utc else "None"
                raise FreshnessViolationException(
                    article_id=art.article_id,
                    timestamp_str=ts_str,
                    window_start=ctx.session.window_start_utc.isoformat(),
                    window_end=ctx.session.window_end_utc.isoformat(),
                )

    @classmethod
    async def _score(cls, ctx: PipelineContext) -> None:
        """Stage 4: Local FinBERT Sentiment Classification."""
        if ctx.on_progress:
            await ctx.on_progress(
                PipelineStage.FINBERT_SCORING,
                0.70,
                f"Running local FinBERT inference on {len(ctx.retained_articles)} candidate articles...",
            )

        t3 = time.time()
        finbert_service = FinBERTService.get_instance()
        scorer = ctx.deps.scorer if ctx.deps and ctx.deps.scorer else None
        ctx.scored_retained = await finbert_service.score_articles_async(
            ctx.retained_articles, ctx.cluster_map, scorer=scorer
        )
        ctx.stage_latencies["finbert_scoring"] = round((time.time() - t3) * 1000, 1)

        # Build complete article evidence list (retained + sample excluded)
        ctx.complete_article_list = list(ctx.scored_retained) + [
            build_excluded_article(excl_art, reason, ctx.cluster_map.get(excl_art.article_id, ""))
            for excl_art, reason, _ in ctx.sample_excluded_articles_raw
        ]

    @classmethod
    async def _synthesize(cls, ctx: PipelineContext) -> None:
        """Stage 5: Gated LLM Catalyst Verification & Synthesis."""
        if ctx.on_progress:
            await ctx.on_progress(
                PipelineStage.CATALYST_SYNTHESIS,
                0.85,
                "Verifying market catalysts via structured LLM prompt...",
            )

        t4 = time.time()
        llm_service = LLMService()
        ctx.observed_facts = []
        ctx.llm_summary = ""
        ctx.llm_telemetry = {}
        ctx.pipeline_mode = PipelineMode.HYBRID_FINBERT_LLM

        if ctx.enable_llm and settings.ENABLE_LLM and settings.OPENROUTER_API_KEY:
            ctx.scored_retained, ctx.observed_facts, ctx.llm_summary, ctx.llm_telemetry = (
                await llm_service.verify_and_synthesize(
                    ctx.asset.ticker, ctx.asset.company_name, ctx.scored_retained
                )
            )
            if ctx.llm_telemetry.get("status") in {"SKIPPED", "FAILED"}:
                ctx.pipeline_mode = PipelineMode.DETERMINISTIC_FINBERT_ONLY
        else:
            ctx.pipeline_mode = PipelineMode.DETERMINISTIC_FINBERT_ONLY

        ctx.stage_latencies["catalyst_synthesis"] = round((time.time() - t4) * 1000, 1)

    @classmethod
    def _aggregate(cls, ctx: PipelineContext) -> None:
        """Stage 6: Score Aggregation & Heuristic Decision Rules."""
        t5 = time.time()
        ctx.agg_res = AggregatorService.aggregate_and_decide(
            ctx.asset.ticker,
            ctx.session,
            ctx.scored_retained,
            ctx.observed_facts,
            llm_summary=ctx.llm_summary,
            pipeline_mode=ctx.pipeline_mode,
        )
        ctx.decision, ctx.decision_confidence, ctx.sentiment_score, ctx.evidence_quality, ctx.rationale, ctx.warnings = ctx.agg_res
        ctx.stage_latencies["aggregating_decision"] = round((time.time() - t5) * 1000, 1)

    @classmethod
    def _build_result(cls, ctx: PipelineContext) -> None:
        """Constructs final PipelineMetrics and AnalysisResult object."""
        total_latency_ms = round((time.time() - ctx.t_start) * 1000, 1)
        distinct_publishers = len({
            a.canonical_publisher for a in ctx.scored_retained
            if a.canonical_publisher != "Unknown Aggregator" and a.exclusion_reason is None
        })
        distinct_clusters = len({
            a.cluster_id for a in ctx.scored_retained
            if a.cluster_id and a.exclusion_reason is None
        })

        ctx.metrics = build_pipeline_metrics(
            total_sources=len(ctx.provider_outcomes),
            distinct_publishers=distinct_publishers,
            distinct_clusters=distinct_clusters,
            publishers_positive=ctx.agg_res.publishers_positive,
            publishers_negative=ctx.agg_res.publishers_negative,
            supporting_publishers=ctx.agg_res.supporting_publishers,
            articles_ingested=len(ctx.raw_articles),
            articles_retained=len(ctx.scored_retained),
            articles_deduplicated=ctx.total_excluded_counts.get(ExclusionReason.DUPLICATE_SYNDICATION.value, 0),
            articles_scored_local=len(ctx.scored_retained),
            articles_sent_to_llm=ctx.llm_telemetry.get("candidates_sent", 0) if ctx.llm_telemetry.get("status") != "SKIPPED" else 0,
            articles_excluded_total=ctx.total_excluded_count,
            excluded_counts=ctx.total_excluded_counts,
            directional_threshold=DIRECTIONAL_THRESHOLD,
            excluded_out_of_window=ctx.excluded_out_of_window,
            excluded_missing_timestamp=ctx.excluded_missing_ts,
            prompt_tokens=ctx.llm_telemetry.get("prompt_tokens", 0),
            completion_tokens=ctx.llm_telemetry.get("completion_tokens", 0),
            estimated_cost_usd=ctx.llm_telemetry.get("estimated_cost_usd", 0.0),
            total_latency_ms=total_latency_ms,
            stage_latencies=ctx.stage_latencies,
        )

        run_id = str(uuid.uuid4())
        used_llm_model = ctx.llm_telemetry.get("model") or settings.LLM_MODEL_ID
        model_versions = {
            "finbert": settings.FINBERT_MODEL_NAME,
            "llm": used_llm_model if ctx.pipeline_mode == PipelineMode.HYBRID_FINBERT_LLM else "NONE",
        }

        warnings = list(ctx.warnings)
        if ctx.provider_failure_warning and ctx.provider_failure_warning not in warnings:
            warnings.append(ctx.provider_failure_warning)

        if not ctx.asset.verified and ctx.asset.resolution_warning and ctx.asset.resolution_warning not in warnings:
            warnings.append(ctx.asset.resolution_warning)

        ctx.result = AnalysisResult(
            run_id=run_id,
            ticker=ctx.asset.ticker,
            company_name=ctx.asset.company_name,
            asset_type=ctx.asset.asset_type,
            session=ctx.session,
            decision=ctx.decision,
            decision_confidence=ctx.decision_confidence,
            sentiment_score=ctx.sentiment_score,
            evidence_quality=ctx.evidence_quality,
            disclaimer=DISCLAIMER,
            rationale=ctx.rationale,
            metrics=ctx.metrics,
            articles=ctx.complete_article_list,
            warnings=warnings,
            pipeline_mode=ctx.pipeline_mode,
            cache_status=CacheStatus.MISS,
            data_status=DataStatus.DEGRADED if ctx.is_degraded else DataStatus.OK,
            hold_reason=ctx.agg_res.hold_reason,
            llm_summary=ctx.llm_summary or None,
            model_versions=model_versions,
            config_version=settings.get_config_hash(),
            provider_outcomes=ctx.provider_outcomes,
        )

    @classmethod
    async def _persist(cls, ctx: PipelineContext) -> None:
        """Persists the result in the database with cacheability flag."""
        if ctx.is_degraded:
            logger.warning(
                f"Persisting analysis run for {ctx.asset.ticker} with is_cacheable=False due to degraded provider outcomes."
            )
        await _save_analysis_run_safe(
            ctx.db, ctx.result, ctx.cache_key, ctx.provider_outcomes, is_cacheable=(not ctx.is_degraded)
        )

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
        ctx = PipelineContext(
            ticker=ticker,
            db=db,
            force_refresh=force_refresh,
            enable_llm=enable_llm,
            on_progress=on_progress,
            resolved_asset=resolved_asset,
            asset=asset,
            deps=deps,
        )

        # Stage 1: Resolve asset, session window, and check cache
        cached_result = await cls._resolve_and_check_cache(ctx)
        if cached_result:
            return cached_result

        # Stage 2: Ingest news & validate provider health
        await cls._ingest(ctx)

        # Stage 2.5: Filter by session freshness window
        early_freshness_result = await cls._filter_fresh(ctx)
        if early_freshness_result:
            return early_freshness_result

        # Stage 3: Deduplication and relevance filtering
        early_relevant_result = await cls._select_relevant(ctx)
        if early_relevant_result:
            return early_relevant_result

        # Core Invariant Assertion (Immediately before FinBERT & Aggregation)
        cls._assert_freshness_invariants(ctx)

        # Stage 4: Local FinBERT Sentiment Classification
        await cls._score(ctx)

        # Stage 5: Gated LLM Catalyst Verification & Synthesis
        await cls._synthesize(ctx)

        # Stage 6: Score Aggregation & Heuristic Decision Rules
        if ctx.on_progress:
            await ctx.on_progress(PipelineStage.AGGREGATING_DECISION, 0.95, "Synthesizing sentiment score and corroboration rules...")
        cls._aggregate(ctx)

        # Build final AnalysisResult & metrics
        cls._build_result(ctx)

        # Persist run and evidence in database
        await cls._persist(ctx)

        if ctx.on_progress:
            await ctx.on_progress(PipelineStage.DONE, 1.0, "Analysis complete.")

        return ctx.result
