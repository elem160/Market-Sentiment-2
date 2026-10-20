from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.core.enums import (
    AssetType,
    CacheStatus,
    DecisionVerdict,
    JobStatus,
    PipelineMode,
    PipelineStage,
    SessionType,
)
from app.core.models import PipelineMetrics, PipelineRationale, ScoredArticle

# SSE Event Names
SSE_EVENT_PROGRESS = "progress"
SSE_EVENT_COMPLETED = "completed"
SSE_EVENT_FAILED = "failed"


class JobProgressEvent(BaseModel):
    job_id: str
    ticker: str
    status: JobStatus
    stage: PipelineStage
    progress_pct: float = Field(ge=0.0, le=1.0)
    message: str


class JobCompletedEvent(BaseModel):
    job_id: str
    status: Literal["COMPLETED"]
    run_id: str
    message: str


class JobFailedEvent(BaseModel):
    job_id: str
    status: Literal["FAILED"]
    error_code: str
    error_message: str


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="US-listed equity or ETF ticker symbol (e.g. AAPL, NVDA, SPY)")
    force_refresh: bool = Field(False, description="Bypass local 15-minute intraday cache if True")
    enable_llm: bool = Field(True, description="Enable LLM catalyst verification and synthesis")


class JobCreatedResponse(BaseModel):
    job_id: str
    ticker: str
    status: JobStatus
    poll_url: str
    events_url: str
    max_wait_seconds: int = 150


class JobStatusResponse(BaseModel):
    job_id: str
    ticker: str
    status: JobStatus
    stage: PipelineStage
    progress_pct: float
    message: str
    run_id: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class RecentRunSummary(BaseModel):
    run_id: str
    ticker: str
    company_name: str
    decision: str
    decision_confidence: float
    sentiment_score: float
    evidence_quality: float
    run_timestamp_utc: str


class HealthResponse(BaseModel):
    status: str
    database_status: str
    finbert_status: str
    llm_configured: bool
    app_env: str
