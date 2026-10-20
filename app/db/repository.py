import json
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.db.models import AnalysisJobDB, AnalysisRunDB, ArticleEvidenceDB, ObservedFactDB
from app.core.models import (
    AnalysisResult,
    ScoredArticle,
    ObservedFact,
    PipelineRationale,
    PipelineMetrics,
)
from app.core.enums import (
    AssetType,
    DecisionVerdict,
    DirectionalPolarity,
    CatalystCategory,
    ProviderType,
    PipelineMode,
    CacheStatus,
    ExclusionReason,
    JobStatus,
    PipelineStage,
    HoldReason,
)
from app.core.session_window import compute_session_window


class SentimentRepository:
    @staticmethod
    def create_job(db: Session, job_id: str, ticker: str, expires_in_hours: int = 2) -> AnalysisJobDB:
        now = datetime.now(timezone.utc)
        job = AnalysisJobDB(
            id=job_id,
            ticker=ticker,
            status=JobStatus.QUEUED.value,
            stage=PipelineStage.RESOLVING_TICKER.value,
            progress_pct=0.05,
            message="Job queued. Initializing analysis pipeline...",
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=expires_in_hours),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def update_job_stage(
        db: Session, job_id: str, stage: PipelineStage, progress_pct: float, message: str
    ):
        job = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
        if job:
            job.status = JobStatus.PROCESSING.value
            job.stage = stage.value
            job.progress_pct = progress_pct
            job.message = message
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

    @staticmethod
    def complete_job(db: Session, job_id: str, run_id: str):
        job = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
        if job:
            job.status = JobStatus.COMPLETED.value
            job.stage = PipelineStage.DONE.value
            job.progress_pct = 1.0
            job.message = "Analysis complete."
            job.run_id = run_id
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

    @staticmethod
    def fail_job(db: Session, job_id: str, error_message: str):
        job = db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED.value
            job.error_message = error_message
            job.message = f"Failed: {error_message}"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

    @staticmethod
    def get_job(db: Session, job_id: str) -> AnalysisJobDB | None:
        return db.query(AnalysisJobDB).filter(AnalysisJobDB.id == job_id).first()

    @staticmethod
    def recover_orphaned_jobs(db: Session) -> int:
        """Mark unfinished jobs as failed upon server startup."""
        orphaned = db.query(AnalysisJobDB).filter(
            AnalysisJobDB.status.in_([JobStatus.QUEUED.value, JobStatus.PROCESSING.value])
        ).all()
        count = len(orphaned)
        for job in orphaned:
            job.status = JobStatus.FAILED.value
            job.error_message = "Server restarted while job was in progress. Please retry."
            job.message = "Terminated due to server restart."
            job.updated_at = datetime.now(timezone.utc)
        if count > 0:
            db.commit()
        return count

    @staticmethod
    def get_cached_run(db: Session, cache_key: str, max_age_seconds: int | None = None) -> AnalysisResult | None:
        run_record = (
            db.query(AnalysisRunDB)
            .filter(AnalysisRunDB.cache_key == cache_key, AnalysisRunDB.is_cacheable.is_(True))
            .order_by(AnalysisRunDB.created_at.desc())
            .first()
        )
        if not run_record:
            return None

        if max_age_seconds is not None:
            now = datetime.now(timezone.utc)
            created = run_record.created_at
            # F-04: If NO_FRESH_NEWS, cap TTL to min(max_age_seconds, 300)
            data_status = getattr(run_record, "data_status", "OK")
            effective_ttl = min(max_age_seconds, 300) if data_status == "NO_FRESH_NEWS" else max_age_seconds
            if (now - created).total_seconds() > effective_ttl:
                return None

        return SentimentRepository._to_analysis_result(run_record, cache_status=CacheStatus.HIT)

    @staticmethod
    def save_analysis_run(
        db: Session,
        result: AnalysisResult,
        cache_key: str,
        provider_outcomes: dict,
        is_cacheable: bool = True,
    ) -> AnalysisRunDB:
        run_record = AnalysisRunDB(
            id=result.run_id,
            ticker=result.ticker,
            company_name=result.company_name,
            asset_type=result.asset_type.value,
            session_type=result.session.session_type.value,
            cache_key=cache_key,
            window_start_utc=result.session.window_start_utc,
            window_end_utc=result.session.window_end_utc,
            run_timestamp_utc=result.session.run_timestamp_utc,
            decision=result.decision.value,
            sentiment_score=result.sentiment_score,
            decision_confidence=result.decision_confidence,
            evidence_quality=result.evidence_quality,
            rationale_summary=result.rationale.summary,
            inferences_json=json.dumps(result.rationale.inferences),
            pipeline_mode=result.pipeline_mode.value,
            model_versions_json=json.dumps(result.model_versions),
            config_version=result.config_version,
            provider_outcomes_json=json.dumps(provider_outcomes),
            cache_status=result.cache_status.value,
            metrics_json=json.dumps(result.metrics.model_dump()),
            warnings_json=json.dumps(result.warnings),
            data_status=result.data_status,
            hold_reason=result.hold_reason.value if result.hold_reason else None,
            llm_summary=result.llm_summary,
            is_cacheable=is_cacheable,
            created_at=datetime.now(timezone.utc),
        )
        db.add(run_record)

        for art in result.articles:
            art_record = ArticleEvidenceDB(
                id=f"{result.run_id}_{art.article_id}",
                article_id=art.article_id,
                run_id=result.run_id,
                provider=art.provider.value,
                source_name=art.source_name,
                canonical_publisher=art.canonical_publisher,
                canonical_url=art.canonical_url,
                title=art.title,
                published_at_utc=art.published_at_utc,
                retrieved_at_utc=datetime.now(timezone.utc),
                lead_text=art.lead_text,
                finbert_positive=art.finbert_positive,
                finbert_negative=art.finbert_negative,
                finbert_neutral=art.finbert_neutral,
                finbert_directional_score=art.finbert_directional_score,
                finbert_confidence=art.finbert_confidence,
                is_llm_catalyst=art.is_llm_catalyst,
                catalyst_category=art.catalyst_category.value if art.catalyst_category else None,
                exclusion_reason=art.exclusion_reason.value if art.exclusion_reason else None,
                final_weight=art.final_weight,
                effective_weight=art.effective_weight,
                age_hours=art.age_hours,
                cluster_id=art.cluster_id,
                publisher_inferred=art.publisher_inferred,
            )
            db.add(art_record)

        for fact in result.rationale.observed_facts:
            fact_record = ObservedFactDB(
                id=str(uuid.uuid4()),
                run_id=result.run_id,
                statement=fact.statement,
                cited_article_id=fact.cited_article_id,
                catalyst_category=fact.catalyst_category.value,
                impact=fact.impact.value,
            )
            db.add(fact_record)

        db.commit()
        db.refresh(run_record)
        return run_record

    @staticmethod
    def get_analysis_run(db: Session, run_id: str) -> AnalysisResult | None:
        run_record = db.query(AnalysisRunDB).filter(AnalysisRunDB.id == run_id).first()
        if not run_record:
            return None
        stored_status = (
            CacheStatus(run_record.cache_status)
            if run_record.cache_status in [cs.value for cs in CacheStatus]
            else CacheStatus.MISS
        )
        return SentimentRepository._to_analysis_result(run_record, cache_status=stored_status)

    @staticmethod
    def get_recent_runs(db: Session, limit: int = 10) -> list[dict]:
        runs = (
            db.query(AnalysisRunDB)
            .order_by(AnalysisRunDB.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "run_id": r.id,
                "ticker": r.ticker,
                "company_name": r.company_name,
                "asset_type": AssetType(r.asset_type) if hasattr(r, "asset_type") and r.asset_type else AssetType.EQUITY,
                "data_status": getattr(r, "data_status", "OK") or "OK",
                "decision": r.decision,
                "decision_confidence": r.decision_confidence,
                "sentiment_score": r.sentiment_score,
                "evidence_quality": r.evidence_quality,
                "hold_reason": getattr(r, "hold_reason", None),
                "run_timestamp_utc": r.run_timestamp_utc,
            }
            for r in runs
        ]

    @staticmethod
    def _to_analysis_result(record: AnalysisRunDB, cache_status: CacheStatus) -> AnalysisResult:
        session = compute_session_window(record.run_timestamp_utc)

        articles = [
            ScoredArticle(
                article_id=getattr(a, "article_id", None) or a.id,
                provider=ProviderType(a.provider),
                source_name=a.source_name,
                canonical_publisher=a.canonical_publisher,
                canonical_url=a.canonical_url,
                title=a.title,
                published_at_utc=a.published_at_utc,
                lead_text=a.lead_text,
                finbert_positive=a.finbert_positive,
                finbert_negative=a.finbert_negative,
                finbert_neutral=a.finbert_neutral,
                finbert_directional_score=a.finbert_directional_score,
                finbert_confidence=a.finbert_confidence,
                is_llm_catalyst=a.is_llm_catalyst,
                catalyst_category=CatalystCategory(a.catalyst_category) if a.catalyst_category else None,
                exclusion_reason=ExclusionReason(a.exclusion_reason) if a.exclusion_reason else None,
                final_weight=a.final_weight,
                effective_weight=getattr(a, "effective_weight", 0.0) or 0.0,
                age_hours=getattr(a, "age_hours", 0.0) or 0.0,
                cluster_id=a.cluster_id,
                publisher_inferred=bool(getattr(a, "publisher_inferred", False)),
            )
            for a in record.articles
        ]

        facts = [
            ObservedFact(
                statement=f.statement,
                cited_article_id=f.cited_article_id,
                catalyst_category=CatalystCategory(f.catalyst_category),
                impact=DirectionalPolarity(f.impact),
            )
            for f in record.facts
        ]

        metrics_dict = json.loads(record.metrics_json) if record.metrics_json else {}
        metrics = PipelineMetrics(**metrics_dict)
        inferences = json.loads(record.inferences_json) if record.inferences_json else []
        warnings = json.loads(record.warnings_json) if record.warnings_json else []
        model_versions = json.loads(record.model_versions_json) if record.model_versions_json else {}

        return AnalysisResult(
            run_id=record.id,
            ticker=record.ticker,
            company_name=record.company_name,
            asset_type=AssetType(record.asset_type),
            session=session,
            decision=DecisionVerdict(record.decision),
            decision_confidence=record.decision_confidence,
            sentiment_score=record.sentiment_score,
            evidence_quality=record.evidence_quality,
            disclaimer="Research & Market Sentiment Tool. Not Financial or Investment Advice.",
            rationale=PipelineRationale(
                summary=record.rationale_summary,
                observed_facts=facts,
                inferences=inferences,
            ),
            metrics=metrics,
            articles=articles,
            warnings=warnings,
            pipeline_mode=PipelineMode(record.pipeline_mode),
            cache_status=cache_status,
            data_status=getattr(record, "data_status", "OK") or "OK",
            hold_reason=HoldReason(record.hold_reason) if getattr(record, "hold_reason", None) else None,
            llm_summary=getattr(record, "llm_summary", None),
            model_versions=model_versions,
            config_version=record.config_version,
        )

