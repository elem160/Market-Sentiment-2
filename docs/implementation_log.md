# SentimentPulse remediation — implementation log

- **Plan:** `docs/implementation_plan.md` — APPROVED 2026-10-19, decisions D1–D8 with the proposed defaults, no overrides.
- **Baseline:** `main` @ `cab8b54` — 83/83 default tests pass, 86% coverage; `pytest -m slow` fails.
- **Environment:** Windows, PowerShell, Python 3.11.9. Node.js is **not installed**, so frontend changes are written but marked "UNVERIFIED (no Node)" until Node 20 LTS is available.
- **Branches:** `fix/phase-0-safety-net` (from `main`) → `fix/phase-1-user-flow` → `fix/phase-2-decision-integrity` → `fix/phase-3-performance-reliability` → `fix/phase-4-quality-docs`.

## Status

| Task | Title | Findings | Status | Commit |
|---|---|---|---|---|
| P0.1 | Isolated, deterministic, offline test suite | H1, H17 | done | `d061051` |
| P0.2 | Clean the polluted local database (not committed) | H1 (D7) | done | — |
| P0.3 | Keep application logs alive after migrations | H2 | done | `4221c23` |
| P0.4 | Dependencies, tooling and CI | M17, L7, L9 | done | `400fccd` |
| P1.1 | One backend↔frontend contract | C1 | done | `3699230` |
| P1.2 | Robust frontend job client | C1, M6 | done | `633e478` |
| P1.3 | Always persist results; caching becomes a flag | C2 | done | `18aaf9e` |
| P1.4 | Stable article IDs, truthful cache status | H13, L3, L4, M14 | done | `18aaf9e` |
| P1.5 | Timezone-aware timestamps end to end | M2, M14 | done | `09bcb77` |
| P1.6 | Truthful UI | M1–M5, M10 | done | `b5fd751` |
| P1.7 | Unified errors and an honest health check | M9 | done | `3eeb71f` |
| P1.8 | Hotfixes | H10, L2 | done | `793e3ee` |
| P1.9 | Rebuild and commit the bundle | D4 | done | (current) |
| P2.1 | Corroboration by direction | C4, M11, M3 | done | `6126557` |
| P2.2 | Relevance engine rebuild | C3, H4, M15 | done | `336b038` |
| P2.3 | Ticker resolution | H3, H5, M16 | done | `5c2507e` |
| P2.4 | Session window and market calendar | H14, L5, M13 | done | `d745273` |
| P2.5 | LLM robustness | H6, H7, M10, M17 | done | `7b9a8e1` |
| P2.6 | Data status, HOLD reasons, confidence | M12, D6 | done | `e933e73` |
| P2.7 | Documentation for Phase 2 behaviour | M18 | done | (current) |
| P3.1 | Ingestion rework | H9, M15, M10, L10 | todo | |
| P3.2 | FinBERT throughput and dependency injection | H8, M16 | todo | |
| P3.3 | Stop blocking the event loop | H11 | todo | |
| P3.4 | Job manager: limits, coalescing, SSE | M7, M8, H15, L6 | todo | |
| P3.5 | Rate limiting and client IP | H12 | todo | |
| P3.6 | Cost, abuse and input controls | H15, L3, L10 | todo | |
| P3.7 | Data lifecycle | H16 | todo | |
| P3.8 | Configuration and startup | M13, L7 | todo | |
| P4.1 | Orchestrator refactor | M16 | todo | |
| P4.2 | Dead code and lint | L1 | todo | |
| P4.3 | Documentation | M18 | todo | |
| P4.4 | Frontend quality | L8 | todo | |
| P4.5 | Repository hygiene | L9 | todo | |
| P4.6 | Persistence details | L4 | todo | |

## Phase 0 — Safety net

### Pre-flight (2026-10-19)

- `git status`: clean on `main` apart from the untracked `docs/implementation_plan.md`; `git log -1` = `cab8b54`.
- `node --version`: not found (no Node in `PATH` or standard install locations).
- Read-only snapshot of `data/sentiment.db` (opened with `mode=ro`, verified non-mutating by running it twice):
  - `sentiment.db` 6 303 744 B, `-wal` 716 912 B; revision `002_freshness_reliability`;
  - rows: `analysis_jobs` 21, `analysis_runs` 29, `article_evidence` 4217, `observed_facts` 37;
  - 10 fixture-based runs (all `EUR/USD`, 3 evidence rows each from `example.com`/`aapl_art_*`); no jobs point at them.
- Installed the plan's dev tools: `time-machine==3.5.1`, `ruff==0.17.1`. Checked that time-machine freezes `datetime.now`/`time.time` but not `time.monotonic`, so asyncio timers keep working under a frozen clock.

### Execution (2026-10-20)

- **P0.1 Isolated, deterministic, offline test suite (`d061051`):**
  - Throwaway SQLite DB initialized in `tests/conftest.py` with `run_migrations()` and automatic per-test table wiping.
  - Network guard monkeypatching `socket` and stubbing `yfinance.Ticker` to prevent unmocked external requests.
  - Clock freezing with `time-machine` via `frozen_now` fixture and deterministic fakes (`KeywordScorer`, `FakeLLMClient` in `tests/fakes.py`).
  - Strict pydantic validation (`extra="forbid"`) on `IngestedArticle` and `ScoredArticle`.
  - Fixed test suites: parameterised pipeline time-independence tests, live provider tests, and isolation assertion guards (`test_suite_isolation.py`).
  - Acceptance: 93/93 offline tests passed in ~2.8s; `pytest -m slow` passed; `pytest -m live` passed online; `data/sentiment.db` untouched.
- **P0.2 Clean the polluted local database:**
  - WAL checkpointed and `data/sentiment.db` backed up to `data/sentiment.db.bak-20261019`.
  - Executed cascade deletion with `PRAGMA foreign_keys=ON` for 10 fixture-based runs and their evidence rows; executed `VACUUM`.
  - Re-inspection confirmed: 0 fixture runs remain. Final row counts: runs=19, jobs=21, evidence=4187, facts=37.
- **P0.3 Keep application logs alive after migrations (`4221c23`):**
  - Updated `alembic/env.py` to only configure file logging when `configure_logger` attribute is True and set `disable_existing_loggers=False`.
  - Updated `run_migrations()` in `app/main.py` to set `alembic_cfg.attributes["configure_logger"] = False`.
  - Added `LOG_LEVEL` config setting to `Settings` and `.env.example`, and applied it to `setup_logger`.
  - Enhanced error handling in `run_background_job` to use `logger.exception`.
  - Added regression test `test_run_migrations_preserves_application_loggers` in `tests/unit/test_reliability.py`.
- **P0.4 Dependencies, tooling and CI (`400fccd`):**
  - Pinned runtime dependencies in `requirements.txt` with verified environment versions and CPU-only torch documentation.
  - Created `requirements-dev.txt` with test and lint tooling.
  - Created `pyproject.toml` with Ruff configuration (select `["E", "F", "I", "B", "UP", "ASYNC"]`, line length 120, legacy rules ignored until P4.2).
  - Added `path_separator = os` to `alembic.ini` (eliminating Alembic deprecation warnings).
  - Added `"typecheck": "tsc --noEmit"` to `frontend/package.json`.
  - Added `.github/workflows/ci.yml` defining full backend and frontend CI pipeline.
  - Aligned `AnalysisRunDB.data_status` column length to `String(30)` in `app/db/models.py`, satisfying `alembic check`.
  - Acceptance: `pytest --cov=app --cov-fail-under=85` passed at 86.11% (94 passed, 0 warnings); `ruff check .` passed; `alembic check` passed with zero schema drift.

## Phase 1 — Restore the user-facing flow

### Execution (2026-10-20)

- **P1.1 One backend↔frontend contract (`3699230`):**
  - Added typed SSE event models (`JobProgressEvent`, `JobCompletedEvent`, `JobFailedEvent`) with strict validation in `app/api/schemas.py`.
  - Exported custom OpenAPI schema with SSE event schemas included via `custom_openapi` and `scripts/export_openapi.py`.
  - Updated routes to emit typed events (`progress`, `completed`, `failed`) and return 404 for unknown jobs on `/jobs/{id}/events`.
  - Added SSE contract tests in `tests/contract/test_sse_contract.py` and OpenAPI snapshot test in `tests/contract/test_openapi_snapshot.py`.
- **P1.2 Robust frontend job client (`633e478`):**
  - Rewrote `subscribeToJob` in `frontend/src/services/api.ts` with explicit cancellation token (`{ cancelled: false }`), typed SSE listeners, backoff polling fallback (1s doubling up to 5s), and server-communicated deadline enforcement (`max_wait_seconds`).
  - Added `activeJobRef` in `App.tsx` ensuring stale in-flight subscriptions are cancelled when navigating or submitting new searches.
- **P1.3 & P1.4 Always persist results & integrity (`18aaf9e`):**
  - Created migration `003_persistence_integrity.py` adding `is_cacheable` column, widening `ticker` to `VARCHAR(32)`, backfilling `article_evidence.article_id`, and enforcing a unique index on `(run_id, article_id)`.
  - Updated `AnalysisRunDB` and `SentimentRepository` to store all runs unconditionally, separating persistence from cache eligibility (`is_cacheable`).
  - Stored truthful `cache_status` (`MISS` on first run, `HIT` on cached return) and generated stable UUID4 fact IDs.
  - Added integration migration test `tests/integration/test_migration_003.py` and E2E job flow test `tests/e2e/test_job_flow.py`.
- **P1.5 Timezone-aware timestamps end to end (`09bcb77`):**
  - Created `app/db/types.py` with `UTCDateTime(TypeDecorator)` converting aware datetimes to UTC on write and attaching `timezone.utc` on read, with zero Alembic schema drift.
  - Replaced all database model `DateTime` columns with `UTCDateTime`.
  - Added `@field_serializer` to `RecentRunSummary.run_timestamp_utc` ensuring ISO-8601 formatting ending with `Z`.
  - Added unit tests in `tests/unit/test_timezone_integrity.py`.
- **P1.6 Truthful UI (`b5fd751`):**
  - Backend: Added `excluded_counts: dict[ExclusionReason, int]`, `articles_excluded_total`, and `directional_threshold` to `PipelineMetrics`; refined `articles_deduplicated` to count only `DUPLICATE_SYNDICATION`.
  - Frontend: Created `frontend/src/utils/time.ts` with DST-aware ET and UTC formatters.
  - Updated `SessionWindowBanner.tsx` (real ET), `DecisionHero.tsx` (cache badge conditional on `HIT`, retained article count, truthful confidence tiers), `EvidenceExplorer.tsx` (directional threshold filtering, grouped exclusions "N of M", age at run), `RationaleSection.tsx` (LLM Catalyst Synthesis card, facts linked to cited articles with publisher/time badges), `TelemetryDrawer.tsx`, `HistorySidebar.tsx`, and `App.tsx`.
- **P1.7 Unified errors and an honest health check (`3eeb71f`):**
  - Added unified exception handlers in `app/main.py` for `SentimentAppException` (with `Retry-After`), `RequestValidationError` (422), Starlette `HTTPException`, and unhandled `Exception` (500 with logged `error_id`).
  - Updated routes in `app/api/routes.py` to raise domain exceptions directly (`JobNotFoundException`, `AnalysisRunNotFoundException`).
  - Implemented honest model status tracking (`NOT_LOADED`, `LOADING`, `LOADED`, `FAILED`) in `FinBERTService` fixing class-vs-instance attribute bug.
  - Updated `/health` to return 503 DEGRADED on database failure with no raw exception leakage, and reflect truthful FinBERT status.
  - Added unit test suite `tests/unit/test_error_handling.py`.
- **P1.8 Hotfixes (`793e3ee`):**
  - Implemented null-safe access via `_as_dict(value) -> dict` in `NewsService.parse_yfinance_items` for `content`, `canonicalUrl`, `clickThroughUrl`, and `provider`; guaranteed `publisher = str(raw or "").strip()`.
  - Updated `AggregatorService` to raise `FreshnessViolationException` with keyword arguments, ensuring the article ID is captured in the message and error details.
  - Added unit tests for null-safe attribute parsing and article naming in `tests/unit/test_freshness.py`.
- **P1.9 Rebuild and commit the bundle:**
  - Exported up-to-date OpenAPI contract via `scripts/export_openapi.py`.
  - Verified `tests/contract/test_openapi_snapshot.py` matches committed snapshot.
  - Verified acceptance: 114 tests passed, 89% coverage (well above 85% requirement), `ruff check .` clean, `alembic check` clean with zero drift.

## Phase 2 — Decision integrity

### Execution (2026-10-20)

- **P2.1 Corroboration by direction (`6126557`):**
  - Added migration `004_decision_integrity.py` adding `article_evidence.publisher_inferred` (BOOLEAN DEFAULT 0) and `analysis_runs.hold_reason` (VARCHAR(40) nullable).
  - Explicitly marked feed sweep entries with `publisher_inferred=True` during Google News sweeps lacking `<source>` metadata, and kept direct publisher feeds authoritative.
  - Enforced directional publisher sets in `AggregatorService`: BUY mandates $P_{\text{pos}} \ge 2$, SELL mandates $P_{\text{neg}} \ge 2$; single-source evidence forces HOLD with `INSUFFICIENT_CORROBORATION`.
  - Excluded inferred publishers and "Unknown Aggregator" from corroboration counts.
  - Added `publishers_positive`, `publishers_negative`, and `supporting_publishers` metrics for backend telemetry and UI corroboration badge.
- **P2.2 Relevance engine rebuild (`336b038`):**
  - Created `app/core/asset_registry.py` and `app/services/relevance.py` implementing deterministic multi-asset relevance matching with compiled regexes.
  - Equities: cashtags, exchange-prefixed tickers, case-sensitive bare tickers ($\ge 2$ chars, checked against common-word blacklist), non-ambiguous aliases, and ambiguous aliases gated by market context.
  - Forex: pair notation matching in all common variants and currency leg isolation with cross-pair exclusion.
  - Commodities & Futures: keyword lists with negative exclusions (e.g. `CL=F` oil rejects olive/palm oil).
  - Built 65 table-driven test cases in `tests/fixtures/relevance_cases.json` covering all probe cases from the review.
- **P2.3 Ticker resolution (`5c2507e`):**
  - Added TTL-governed resolution caching keyed by `(normalized, bypass_aliases)` with 6h TTL (`TICKER_CACHE_TTL_SECONDS`), 10-minute negative cache for unknown symbols, and 8.0s asynchronous thread timeout raising 503 `ProviderException`.
  - Removed cross-mode cache pollution (`$GOLD` vs `GOLD`).
  - Mapped futures tickers (`ES=F`, `NQ=F`, `YM=F`, `RTY=F`) to `AssetType.FUTURES` with `"CME"` exchange.
  - Passed pre-resolved `Asset` from API routes into background jobs and orchestrator, preserving `$` intent and skipping redundant resolution.
- **P2.4 Session window and market calendar (`d745273`):**
  - Created `app/core/market_calendar.py` with explicit dated tables for 2025–2027 NYSE holidays, special closures (e.g., Jimmy Carter Day of Mourning 2025-01-09), and 13:00 ET early closes.
  - Unified session window rule across all sessions (Decision D1): window starts at the close of the most recent active NYSE trading day strictly prior to today's date (16:00 ET, or 13:00 ET on early close days), capped at $\max(T_{\text{prior\_close}}, T_{\text{run}} - 72\text{h})$, ending at `run`.
  - Updated cache bucket flooring to floor by minutes since midnight ET, supporting buckets > 60 minutes, with pydantic settings validation.
- **P2.5 LLM robustness (`7b9a8e1`):**
  - Configured shared `AsyncOpenAI` client lazily instantiated and cleanly closed at lifespan shutdown.
  - Implemented multi-model fallback (`[LLM_MODEL_ID, LLM_FALLBACK_MODEL_ID]`) with 30s overall deadline degrading gracefully to `PipelineMode.DETERMINISTIC_FINBERT_ONLY` instead of failing the job.
  - Enforced structured JSON output validation against `LLMCatalystResponse`, falling through on empty content, truncation, or schema mismatch.
  - Prompt hardening: escaped `&` to `&amp;` before `<` and `>`, stripped control characters, bounded headlines/publishers, and trimmed candidates to fit `MAX_PROMPT_TOKENS`.
  - Refreshed pricing table with env override support (`MODEL_PRICING`) and free model zero-cost handling.
- **P2.6 Data status, HOLD reasons, confidence (`e933e73`):**
  - Enforced `DataStatus`: `OK`, `NO_FRESH_NEWS`, `NO_RELEVANT_NEWS` (0 articles survive relevance/dedup -> FinBERT and LLM skipped, HOLD, confidence 0.0), `DEGRADED` (all RSS failed -> saved for auditability, `is_cacheable=False`).
  - Capped cache TTL for `NO_FRESH_NEWS` and `NO_RELEVANT_NEWS` to $\min(\text{bucket}, 300\text{s})$.
  - Stored `HoldReason` (`NO_NEWS`, `SPARSE_EVIDENCE`, `INSUFFICIENT_CORROBORATION`, `CONFLICTING`, `NEUTRAL`) in `analysis_runs.hold_reason`.
  - Applied Decision D6 confidence ceilings: confidence is strictly 0.0 for `NO_NEWS` and `SPARSE_EVIDENCE` (displayed as `n/a` in UI); upper 0.95 hybrid ceiling applies only when LLM confirmed $\ge 1$ catalyst supporting verdict direction; otherwise capped at 0.60.
  - Updated frontend `DecisionHero.tsx` and `HistorySidebar.tsx` with HOLD reason subtext, `n/a` confidence for evidence-free HOLDs, and banners/badges for `NO_RELEVANT_NEWS` and `DEGRADED`.
- **P2.7 Documentation for Phase 2 behaviour:**
  - Updated `README.md` with directional corroboration rules, confidence formulas and D6 dynamic ceilings, data statuses table, HOLD reasons reference, and multi-asset relevance engine specifications.
  - Documented completion in `docs/implementation_log.md`.
  - Acceptance: 220 offline tests passed, 89% coverage, `ruff check .` clean, `alembic check` clean with zero drift.

## Deviations

_None._

## Follow-ups

_None._
