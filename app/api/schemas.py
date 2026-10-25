from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_serializer

from app.core.enums import (
    AssetType,
    DataStatus,
    HoldReason,
    JobStatus,
    PipelineStage,
)

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
    ticker: str = Field(..., min_length=1, max_length=20, description="US-listed equity or ETF ticker symbol (e.g. AAPL, NVDA, SPY)")
    force_refresh: bool = Field(False, description="Bypass local 15-minute intraday cache if True")
    enable_llm: bool = Field(True, description="Enable LLM catalyst verification and synthesis")


class JobCreatedResponse(BaseModel):
    job_id: str
    ticker: str
    status: JobStatus
    poll_url: str
    events_url: str
    max_wait_seconds: int = 150
    coalesced: bool = False


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
    asset_type: AssetType = AssetType.EQUITY
    data_status: DataStatus = DataStatus.OK
    decision: str
    decision_confidence: float
    sentiment_score: float
    evidence_quality: float
    hold_reason: HoldReason | None = None
    run_timestamp_utc: datetime

    @field_serializer("run_timestamp_utc")
    def serialize_run_timestamp(self, dt: datetime, _info) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class HealthResponse(BaseModel):
    status: str
    database_status: str
    finbert_status: str
    llm_configured: bool
    app_env: str
