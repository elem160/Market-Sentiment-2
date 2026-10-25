# Changelog

All notable changes to the Market Sentiment intelligence platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2026-10-25

### Added
- **Multi-Asset Ingestion & Health Tracking**:
  - Concurrent feed ingestion via `asyncio.gather` for Yahoo Finance API and Google News RSS aggregator feeds.
  - Dedicated Forex RSS providers (`Investing.com`, `FXStreet`) for currency pair resolution.
  - Granular provider outcome tracking (`ProviderOutcome`) recording status, HTTP/parse latency, article counts, and error codes (`ProviderKind.YFINANCE`, `ProviderKind.RSS_GOOGLE`, `ProviderKind.RSS_DIRECT`).
  - Clear `data_status` taxonomy: `OK`, `NO_FRESH_NEWS`, `NO_RELEVANT_NEWS`, and `DEGRADED` (for feed outages).
- **Session Windows & NYSE Calendar (Decision D1)**:
  - Unified session window anchoring pre-market and overnight sweeps to the previous trading day's close (16:00 ET, or 13:00 ET on early close days), capturing post-close earnings announcements and weekend developments.
  - Timezone-aware timestamp handling throughout (`America/New_York` and `UTCDateTime`).
- **Directional Corroboration & Decision Integrity**:
  - Two-publisher corroboration rule: BUY verdicts strictly require $\ge 2$ distinct eligible canonical publishers on the positive side; SELL verdicts require $\ge 2$ on the negative side.
  - Feed sweeps with `publisher_inferred=True` or `Unknown Aggregator` excluded from corroboration counts.
  - 5-tiered `HoldReason` enum: `NO_NEWS`, `SPARSE_EVIDENCE`, `INSUFFICIENT_CORROBORATION`, `CONFLICTING`, and `NEUTRAL`.
  - Dynamic confidence ceiling (Decision D6): bounded to $[0.15, 0.60]$ without verified catalysts or under FinBERT-only fallback; elevated up to $0.95$ when LLM verifies market-moving catalysts in verdict direction.
- **FinBERT Throughput & Protocol Abstraction**:
  - Batched FinBERT inference via `SentimentScorer` protocol (`FinBERTScorer` and test `KeywordScorer`).
  - Double tokenization eliminated; background warmup during application lifespan.
- **Non-Blocking Architecture & Concurrency Control**:
  - Dedicated worker thread pools: `db_executor` for SQLite writes and `io_executor` for network requests, keeping FastAPI event loop responsive (<200 ms latency under concurrent load).
  - Centralized `JobManager` with concurrency semaphore (`MAX_CONCURRENT_PIPELINES=2`), queue position tracking, and FIFO queue timeout (`JOB_QUEUE_TIMEOUT_SECONDS=120s`).
  - Request coalescing: concurrent requests for identical ticker and session bucket share a single background job (`coalesced: true`).
  - Real-time Server-Sent Events (SSE) with stage percentage progress events (`event: progress`) and periodic keepalive comments (`: ping\n\n` every 15s).
- **Security & Abuse Controls**:
  - Scoped sliding-window rate limiting (`analyze` 15/min, `jobs` 60/min, `read` 120/min) with bounded LRU key store (`max_keys=10000`).
  - Right-to-left `X-Forwarded-For` proxy IP resolution supporting CIDR trusted ranges (`TRUSTED_PROXY_IPS`).
  - Optional API key authentication (`API_KEY`) and gated history inspection (`PUBLIC_HISTORY=False`).
  - Daily LLM spend capping (`LLM_DAILY_BUDGET_USD`), gracefully degrading to FinBERT-only classification when budget is exhausted.
  - Strict input length validation on tickers ($\le 20$ characters) with 422 `RequestValidationError`.
  - Security headers middleware (`X-Content-Type-Options`, `Referrer-Policy`, CSP) and restricted CORS.
- **Data Lifecycle & Operations**:
  - Sample exclusion capping (`MAX_EXCLUDED_SAMPLES_PER_REASON=20`), preserving total exclusion metrics while keeping SQLite storage bounded.
  - Automatic hourly background maintenance worker purging expired jobs and runs older than `RUN_RETENTION_DAYS=30` with cascading cleanup of evidence and facts.
  - Command-line maintenance runner: `python -m app.cli maintenance [--vacuum] [--retention-days N]`.
  - Application entry point runner: `python -m app` running uvicorn with configured host, port, single-worker deployment, and proxy settings.
- **Code Quality & Testing**:
  - Decomposed `AnalysisOrchestrator` into modular `PipelineContext` stages.
  - Golden snapshot integration test guarding contract invariants.
  - Strict Ruff lint rules with zero warnings.
  - Comprehensive 284-test backend offline test suite (coverage $\ge 86\%$) and 14-test frontend suite.

### Changed
- Refactored `AggregatorService.aggregate_and_decide` to remove unused `company_name` parameter.
- Upgraded cache key algorithm to `ALGORITHM_VERSION=2` incorporating `asset_type` and configuration hash.
- Updated database migrations:
  - `003_persistence_integrity`: unique constraint on `(run_id, article_id)`, `is_cacheable` flag.
  - `004_decision_integrity`: `publisher_inferred` flag and `hold_reason` column.
  - `005_operations`: `llm_cost_usd` column and operational indexes on `created_at` and `expires_at`.
- Refactored frontend to consume v1.1.0 SSE contract (`event: progress`, `hold_reason`, `data_status`).

### Removed
- Removed unused exceptions: `UnsupportedAssetException`, `BudgetExceededException`.
- Removed dead enum values: `AssetType.INDEX`, `ProviderType.FINNHUB`, `ExclusionReason.CATALYST_REJECTED_AS_NOISE`.
- Removed deprecated `TickerLockManager` (replaced by `JobManager`).
- Removed unused `HttpUrl` imports and legacy synthesis structures.
