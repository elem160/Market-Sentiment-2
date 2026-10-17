from datetime import datetime
from pydantic import BaseModel, Field
from app.core.enums import DecisionVerdict, AssetType, SessionType, PipelineMode, CacheStatus
from app.core.models import PipelineRationale, PipelineMetrics, ScoredArticle


class AnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="US-listed equity or ETF ticker symbol (e.g. AAPL, NVDA, SPY)")
    force_refresh: bool = Field(False, description="Bypass local 15-minute intraday cache if True")
    enable_llm: bool = Field(True, description="Enable LLM catalyst verification and synthesis")


class JobCreatedResponse(BaseModel):
    job_id: str
    ticker: str
    status: str
    poll_url: str
    events_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    ticker: str
    status: str
    stage: str
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
