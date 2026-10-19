import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.database import Base


class AnalysisJobDB(Base):
    __tablename__ = "analysis_jobs"

    id = Column(String(36), primary_key=True)  # UUIDv4
    ticker = Column(String(10), index=True, nullable=False)
    status = Column(String(20), nullable=False, default="QUEUED")  # QUEUED, PROCESSING, COMPLETED, FAILED
    stage = Column(String(30), nullable=False, default="RESOLVING_TICKER")
    progress_pct = Column(Float, default=0.0)
    message = Column(Text, default="")
    run_id = Column(String(36), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class AnalysisRunDB(Base):
    __tablename__ = "analysis_runs"

    id = Column(String(36), primary_key=True)  # UUIDv4
    ticker = Column(String(10), index=True, nullable=False)
    company_name = Column(String(255), nullable=False)
    asset_type = Column(String(20), nullable=False, default="EQUITY")
    session_type = Column(String(30), nullable=False)
    cache_key = Column(String(64), index=True, nullable=False)

    window_start_utc = Column(DateTime, nullable=False)
    window_end_utc = Column(DateTime, nullable=False)
    run_timestamp_utc = Column(DateTime, nullable=False)

    decision = Column(String(10), nullable=False)  # BUY, HOLD, SELL
    sentiment_score = Column(Float, nullable=False)
    decision_confidence = Column(Float, nullable=False)
    evidence_quality = Column(Float, nullable=False)

    rationale_summary = Column(Text, nullable=False)
    inferences_json = Column(Text, nullable=False, default="[]")

    pipeline_mode = Column(String(30), nullable=False)  # HYBRID_FINBERT_LLM, DETERMINISTIC_FINBERT_ONLY
    model_versions_json = Column(Text, nullable=False, default="{}")
    config_version = Column(String(32), nullable=False)
    provider_outcomes_json = Column(Text, nullable=False, default="{}")
    cache_status = Column(String(10), nullable=False, default="MISS")

    metrics_json = Column(Text, nullable=False, default="{}")
    warnings_json = Column(Text, nullable=False, default="[]")
    data_status = Column(String(20), nullable=False, default="OK")
    llm_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    articles = relationship("ArticleEvidenceDB", back_populates="run", cascade="all, delete-orphan")
    facts = relationship("ObservedFactDB", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_runs_ticker_created", "ticker", "created_at"),
    )


class ArticleEvidenceDB(Base):
    __tablename__ = "article_evidence"

    id = Column(String(64), primary_key=True)  # Deterministic hash
    run_id = Column(String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    provider = Column(String(30), nullable=False)
    source_name = Column(String(100), nullable=False)
    canonical_publisher = Column(String(100), nullable=False)
    canonical_url = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    published_at_utc = Column(DateTime, nullable=True)
    retrieved_at_utc = Column(DateTime, nullable=False)
    lead_text = Column(Text, nullable=False)

    finbert_positive = Column(Float, nullable=False)
    finbert_negative = Column(Float, nullable=False)
    finbert_neutral = Column(Float, nullable=False)
    finbert_directional_score = Column(Float, nullable=False)
    finbert_confidence = Column(Float, nullable=False)

    is_llm_catalyst = Column(Boolean, default=False)
    catalyst_category = Column(String(30), nullable=True)
    exclusion_reason = Column(String(40), nullable=True)
    final_weight = Column(Float, default=0.0)
    effective_weight = Column(Float, default=0.0)
    age_hours = Column(Float, default=0.0)
    cluster_id = Column(String(64), default="")

    run = relationship("AnalysisRunDB", back_populates="articles")



class ObservedFactDB(Base):
    __tablename__ = "observed_facts"

    id = Column(String(36), primary_key=True)  # UUIDv4
    run_id = Column(String(36), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True, nullable=False)
    statement = Column(Text, nullable=False)
    cited_article_id = Column(String(64), nullable=False)
    catalyst_category = Column(String(30), nullable=False)
    impact = Column(String(20), nullable=False)

    run = relationship("AnalysisRunDB", back_populates="facts")
