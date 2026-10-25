from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import DIRECTIONAL_THRESHOLD
from app.core.enums import (
    AssetType,
    CacheStatus,
    CatalystCategory,
    DataStatus,
    DecisionVerdict,
    DirectionalPolarity,
    ExclusionReason,
    HoldReason,
    PipelineMode,
    ProviderKind,
    ProviderType,
)
from app.core.session_window import SessionWindow


@dataclass
class FeedSpec:
    key: str
    kind: ProviderKind
    url: str
    publisher: str
    provider_type: ProviderType
    publisher_is_authoritative: bool = False
    enabled: bool = True


class ProviderOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    kind: ProviderKind
    status: str                         # "SUCCESS" | "FAILED" | "TIMEOUT"
    count: int = 0
    latency_ms: float = 0.0
    error_code: str | None = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)



@dataclass
class PipelineDeps:
    http_client: Any = None
    scorer: Any = None
    llm_service: Any = None
    session_factory: Any = None
    io_executor: Any = None
    db_executor: Any = None



@dataclass
class Asset:
    ticker: str
    company_name: str
    exchange: str
    sector: str = ""
    asset_type: AssetType = AssetType.EQUITY
    is_active: bool = True
    yf_symbol: str = ""
    verified: bool = True
    resolution_warning: str | None = None


class IngestedArticle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str                      # Deterministic hash of canonical_url + title
    provider: ProviderType               # YFINANCE | GOOGLE_RSS_AGGREGATOR | FIXTURE | INVESTING_FOREX_RSS | FXSTREET_RSS
    source_name: str                     # e.g., "Reuters", "CNBC", "PR Newswire"
    canonical_url: str                   # Cleaned URL without utm_* tracking
    title: str                           # Sanitized headline
    summary: str = ""                    # Summary or lead text (max 1000 chars)
    published_at_utc: datetime | None = None # None means missing or untrusted
    retrieved_at_utc: datetime           # Timestamp when ingested
    raw_provider_metadata: dict = Field(default_factory=dict)


class ScoredArticle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_id: str
    provider: ProviderType
    source_name: str
    canonical_publisher: str             # Normalized publisher root entity
    publisher_inferred: bool = False     # True if inferred from default feed name rather than explicit source tag
    canonical_url: str
    title: str
    published_at_utc: datetime | None = None # Timezone-aware UTC timestamp or None if undated
    retrieved_at_utc: datetime | None = None # Timezone-aware UTC timestamp when ingested
    lead_text: str
    finbert_positive: float
    finbert_negative: float
    finbert_neutral: float
    finbert_directional_score: float     # In [-1.0, 1.0]
    finbert_confidence: float            # In [0.0, 1.0]
    is_llm_catalyst: bool = False
    catalyst_category: CatalystCategory | None = None
    exclusion_reason: ExclusionReason | None = None
    final_weight: float = 0.0
    effective_weight: float = 0.0        # recency_decay * max(0.2, final_weight)
    age_hours: float = 0.0               # Hours elapsed from publication to session run
    cluster_id: str = ""                 # Group ID for syndicated articles


class ObservedFact(BaseModel):
    statement: str
    cited_article_id: str                # Must match a retained ScoredArticle ID
    catalyst_category: CatalystCategory
    impact: DirectionalPolarity


class PipelineRationale(BaseModel):
    summary: str
    observed_facts: list[ObservedFact] = []
    inferences: list[str] = []

class PipelineMetrics(BaseModel):
    total_sources: int = 0
    distinct_publishers: int = 0
    distinct_clusters: int = 0
    publishers_positive: int = 0
    publishers_negative: int = 0
    supporting_publishers: int = 0
    articles_ingested: int = 0
    articles_retained: int = 0
    articles_deduplicated: int = 0
    articles_scored_local: int = 0
    articles_sent_to_llm: int = 0
    articles_excluded_total: int = 0
    excluded_counts: dict[str, int] = Field(default_factory=dict)
    directional_threshold: float = DIRECTIONAL_THRESHOLD
    excluded_out_of_window: int = 0
    excluded_missing_timestamp: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
    stage_latencies: dict[str, float] = {}


class AnalysisResult(BaseModel):
    run_id: str
    ticker: str
    company_name: str
    asset_type: AssetType
    session: SessionWindow
    decision: DecisionVerdict
    decision_confidence: float           # In [0.0, 1.0]
    sentiment_score: float               # In [-1.0, 1.0]
    evidence_quality: float              # In [0.0, 1.0]
    disclaimer: str
    rationale: PipelineRationale
    metrics: PipelineMetrics
    articles: list[ScoredArticle]
    warnings: list[str] = []
    pipeline_mode: PipelineMode = PipelineMode.HYBRID_FINBERT_LLM
    cache_status: CacheStatus = CacheStatus.MISS
    data_status: DataStatus = DataStatus.OK
    hold_reason: HoldReason | None = None
    llm_summary: str | None = None
    model_versions: dict[str, str] = {}
    config_version: str = ""
    provider_outcomes: list[ProviderOutcome] = Field(default_factory=list)

    @field_validator("provider_outcomes", mode="before")
    @classmethod
    def normalize_provider_outcomes(cls, v: Any) -> list[ProviderOutcome]:
        if isinstance(v, dict):
            res = []
            for k, val in v.items():
                if k == "google_news_rss_total":
                    continue
                val_dict = val if isinstance(val, dict) else {}
                kind = (
                    ProviderKind.YFINANCE if k == "yfinance"
                    else ProviderKind.RSS_DIRECT if k.startswith("forex_")
                    else ProviderKind.RSS_GOOGLE
                )
                res.append(
                    ProviderOutcome(
                        key=k,
                        kind=kind,
                        status=val_dict.get("status", "SUCCESS"),
                        count=val_dict.get("count", 0),
                        latency_ms=val_dict.get("latency_ms", 0.0),
                        error_code=val_dict.get("error"),
                    )
                )
            return res
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, ProviderOutcome):
                    res.append(item)
                elif isinstance(item, dict):
                    res.append(ProviderOutcome(**item))
            return res
        return []


