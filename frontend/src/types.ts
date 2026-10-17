export type DecisionVerdict = 'BUY' | 'HOLD' | 'SELL';

export type PipelineStage =
  | 'VALIDATING_TICKER'
  | 'FETCHING_NEWS'
  | 'DEDUPLICATING'
  | 'SCORING_FINBERT'
  | 'EXTRACTING_CATALYSTS'
  | 'AGGREGATING_DECISION'
  | 'FINALIZING'
  | string;

export interface ScoredArticle {
  article_id: string;
  provider: string;
  source_name: string;
  canonical_publisher: string;
  canonical_url: string;
  title: string;
  published_at_utc: string;
  lead_text?: string;
  finbert_positive: number;
  finbert_negative: number;
  finbert_neutral: number;
  finbert_directional_score: number;
  finbert_confidence: number;
  is_llm_catalyst?: boolean;
  catalyst_category?: string | null;
  exclusion_reason?: string | null;
  final_weight: number;
  cluster_id: string;
}

export interface ObservedFact {
  fact_id?: string;
  statement: string;
  source_article_id?: string;
  source_publisher: string;
  published_at_utc: string;
}

export interface PipelineRationale {
  summary: string;
  observed_facts: ObservedFact[];
  inferences: string[];
}

export interface SessionWindow {
  market_timezone: string;
  session_type: string;
  is_market_open: boolean;
  window_start_utc: string;
  window_start_et: string;
  window_end_utc: string;
  window_end_et: string;
  window_duration_hours: number;
  run_timestamp_utc: string;
  run_timestamp_et: string;
}

export interface PipelineMetrics {
  total_sources: number;
  distinct_publishers: number;
  distinct_clusters: number;
  articles_ingested: number;
  articles_retained: number;
  articles_deduplicated: number;
  articles_scored_local: number;
  articles_sent_to_llm: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  total_latency_ms: number;
  stage_latencies: Record<string, number>;
}

export interface AnalysisResult {
  run_id: string;
  ticker: string;
  company_name: string;
  asset_type: string;
  session: SessionWindow;
  decision: DecisionVerdict;
  decision_confidence: number;
  sentiment_score: number;
  evidence_quality: number;
  disclaimer: string;
  rationale: PipelineRationale;
  metrics: PipelineMetrics;
  articles: ScoredArticle[];
  warnings: string[];
  pipeline_mode: string;
  cache_status: string;
  model_versions: Record<string, string>;
  config_version: string;
}

export interface JobProgressEvent {
  job_id: string;
  ticker: string;
  stage: string;
  progress_pct: number;
  message: string;
  status: string;
  run_id?: string | null;
  result?: AnalysisResult | null;
  error?: string | null;
  error_message?: string | null;
}

export interface HistoryItem {
  run_id: string;
  ticker: string;
  company_name: string;
  decision: DecisionVerdict;
  decision_confidence: number;
  sentiment_score: number;
  evidence_quality: number;
  run_timestamp_utc: string;
}
