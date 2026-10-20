/**
 * This file was generated from OpenAPI schema snapshot (frontend/src/api/openapi.json).
 */

export interface paths {
  "/api/v1/analyze": {
    post: {
      requestBody: {
        content: {
          "application/json": components["schemas"]["AnalyzeRequest"];
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["AnalysisResult"];
          };
        };
        202: {
          content: {
            "application/json": components["schemas"]["JobCreatedResponse"];
          };
        };
        422: {
          content: {
            "application/json": components["schemas"]["HTTPValidationError"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}": {
    get: {
      parameters: {
        path: {
          job_id: string;
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["JobStatusResponse"];
          };
        };
        404: {
          content: {
            "application/json": unknown;
          };
        };
        422: {
          content: {
            "application/json": components["schemas"]["HTTPValidationError"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}/events": {
    get: {
      parameters: {
        path: {
          job_id: string;
        };
      };
      responses: {
        200: {
          content: {
            "text/event-stream": string;
          };
        };
        404: {
          content: {
            "application/json": unknown;
          };
        };
      };
    };
  };
  "/api/v1/analysis/{run_id}": {
    get: {
      parameters: {
        path: {
          run_id: string;
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["AnalysisResult"];
          };
        };
        404: {
          content: {
            "application/json": unknown;
          };
        };
      };
    };
  };
  "/api/v1/history": {
    get: {
      parameters: {
        query?: {
          limit?: number;
        };
      };
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["RecentRunSummary"][];
          };
        };
      };
    };
  };
  "/health": {
    get: {
      responses: {
        200: {
          content: {
            "application/json": components["schemas"]["HealthResponse"];
          };
        };
      };
    };
  };
}

export interface components {
  schemas: {
    AnalysisResult: {
      run_id: string;
      ticker: string;
      company_name: string;
      asset_type: components["schemas"]["AssetType"] | string;
      session: components["schemas"]["SessionWindow"];
      decision: components["schemas"]["DecisionVerdict"];
      decision_confidence: number;
      sentiment_score: number;
      evidence_quality: number;
      disclaimer: string;
      rationale: components["schemas"]["PipelineRationale"];
      metrics: components["schemas"]["PipelineMetrics"];
      articles: components["schemas"]["ScoredArticle"][];
      warnings: string[];
      pipeline_mode: components["schemas"]["PipelineMode"] | string;
      cache_status: components["schemas"]["CacheStatus"] | string;
      data_status?: components["schemas"]["DataStatus"];
      hold_reason?: components["schemas"]["HoldReason"] | null;
      llm_summary?: string | null;
      model_versions: Record<string, string>;
      config_version: string;
    };
    AnalyzeRequest: {
      ticker: string;
      force_refresh?: boolean;
      enable_llm?: boolean;
    };
    AssetType: "EQUITY" | "ETF" | "FOREX" | "COMMODITY" | "FUTURES" | "CRYPTO" | "INDEX";
    CacheStatus: "HIT" | "MISS";
    DataStatus: "OK" | "NO_FRESH_NEWS" | "NO_RELEVANT_NEWS" | "DEGRADED";
    CatalystCategory:
      | "EARNINGS"
      | "M_AND_A"
      | "REGULATORY"
      | "PRODUCT_EXECUTION"
      | "MACRO"
      | "ANALYST_ACTION"
      | "LITIGATION"
      | "OTHER";
    DecisionVerdict: "BUY" | "HOLD" | "SELL";
    DirectionalPolarity: "POSITIVE" | "NEGATIVE" | "NEUTRAL";
    ExclusionReason:
      | "MISSING_OR_UNTRUSTED_TIMESTAMP"
      | "TIMESTAMP_OUT_OF_WINDOW"
      | "DUPLICATE_SYNDICATION"
      | "INSUFFICIENT_ENTITY_RELEVANCE"
      | "CATALYST_REJECTED_AS_NOISE"
      | "CAPACITY_LIMIT";
    HTTPValidationError: {
      detail?: components["schemas"]["ValidationError"][];
    };
    HealthResponse: {
      status: string;
      database_status: string;
      finbert_status: string;
      llm_configured: boolean;
      app_env: string;
    };
    JobCompletedEvent: {
      job_id: string;
      status: "COMPLETED";
      run_id: string;
      message: string;
    };
    JobCreatedResponse: {
      job_id: string;
      ticker: string;
      status: components["schemas"]["JobStatus"];
      poll_url: string;
      events_url: string;
      max_wait_seconds?: number;
    };
    HoldReason:
      | "NO_NEWS"
      | "SPARSE_EVIDENCE"
      | "INSUFFICIENT_CORROBORATION"
      | "CONFLICTING"
      | "NEUTRAL";
    JobFailedEvent: {
      job_id: string;
      status: "FAILED";
      error_code: string;
      error_message: string;
    };
    JobProgressEvent: {
      job_id: string;
      ticker: string;
      status: components["schemas"]["JobStatus"];
      stage: components["schemas"]["PipelineStage"];
      progress_pct: number;
      message: string;
    };
    JobStatus: "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED";
    JobStatusResponse: {
      job_id: string;
      ticker: string;
      status: components["schemas"]["JobStatus"];
      stage: components["schemas"]["PipelineStage"];
      progress_pct: number;
      message: string;
      run_id?: string | null;
      error_message?: string | null;
      created_at: string;
      updated_at: string;
    };
    ObservedFact: {
      statement: string;
      cited_article_id?: string | null;
      catalyst_category?: string | null;
      impact?: string | null;
    };
    PipelineMetrics: {
      total_sources: number;
      distinct_publishers: number;
      distinct_clusters: number;
      publishers_positive?: number;
      publishers_negative?: number;
      supporting_publishers?: number;
      articles_ingested: number;
      articles_retained: number;
      articles_deduplicated: number;
      articles_scored_local: number;
      articles_sent_to_llm: number;
      articles_excluded_total?: number;
      excluded_counts?: Record<string, number>;
      directional_threshold?: number;
      excluded_out_of_window?: number;
      excluded_missing_timestamp?: number;
      prompt_tokens: number;
      completion_tokens: number;
      estimated_cost_usd: number;
      total_latency_ms: number;
      stage_latencies: Record<string, number>;
    };
    PipelineMode: "HYBRID_FINBERT_LLM" | "DETERMINISTIC_FINBERT_ONLY";
    PipelineRationale: {
      summary: string;
      observed_facts: components["schemas"]["ObservedFact"][];
      inferences: string[];
    };
    PipelineStage:
      | "RESOLVING_TICKER"
      | "INGESTING_NEWS"
      | "FILTERING_DEDUPLICATING"
      | "FINBERT_SCORING"
      | "CATALYST_SYNTHESIS"
      | "AGGREGATING_DECISION"
      | "DONE";
    ProviderType:
      | "YFINANCE"
      | "FINNHUB"
      | "GOOGLE_RSS_AGGREGATOR"
      | "INVESTING_FOREX_RSS"
      | "FXSTREET_RSS"
      | "FIXTURE";
    RecentRunSummary: {
      run_id: string;
      ticker: string;
      company_name: string;
      asset_type?: components["schemas"]["AssetType"] | string;
      data_status?: components["schemas"]["DataStatus"];
      decision: string;
      decision_confidence: number;
      sentiment_score: number;
      evidence_quality: number;
      hold_reason?: components["schemas"]["HoldReason"] | null;
      run_timestamp_utc: string;
    };
    ScoredArticle: {
      article_id: string;
      provider: components["schemas"]["ProviderType"] | string;
      source_name: string;
      canonical_publisher: string;
      publisher_inferred?: boolean;
      canonical_url: string;
      title: string;
      published_at_utc?: string | null;
      lead_text: string;
      finbert_positive: number;
      finbert_negative: number;
      finbert_neutral: number;
      finbert_directional_score: number;
      finbert_confidence: number;
      is_llm_catalyst?: boolean;
      catalyst_category?: components["schemas"]["CatalystCategory"] | string | null;
      exclusion_reason?: components["schemas"]["ExclusionReason"] | string | null;
      final_weight: number;
      effective_weight?: number | null;
      age_hours?: number | null;
      cluster_id: string;
    };
    SessionType:
      | "PRE_MARKET"
      | "REGULAR_HOURS"
      | "POST_MARKET"
      | "OVERNIGHT_PRE_OPEN"
      | "WEEKEND_SESSION"
      | "HOLIDAY_OFF_MARKET";
    SessionWindow: {
      market_timezone: string;
      session_type: components["schemas"]["SessionType"] | string;
      is_market_open: boolean;
      window_start_utc: string;
      window_start_et: string;
      window_end_utc: string;
      window_end_et: string;
      window_duration_hours: number;
      run_timestamp_utc: string;
      run_timestamp_et: string;
    };
    ValidationError: {
      loc: (string | number)[];
      msg: string;
      type: string;
      ctx?: Record<string, unknown>;
    };
  };
}
