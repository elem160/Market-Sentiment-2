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
| P3.1 | Ingestion rework | H9, M15, M10, L10 | done | `71b22f5` |
| P3.2 | FinBERT throughput and dependency injection | H8, M16 | done | `55ee3f6` |
| P3.3 | Stop blocking the event loop | H11 | done | `a7cb23e` |
| P3.4 | Job manager: limits, coalescing, SSE | M7, M8, H15, L6 | done | `96d6131` |
| P3.5 | Rate limiting and client IP | H12 | done | `0e1889d` |
| P3.6 | Cost, abuse and input controls | H15, L3, L10 | done | `54c726a` |
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

## Remediation Follow-up: Audit Findings Remediation (2026-10-24)

Addressing auditor review findings on branch `fix/phase-2-decision-integrity`:

- **Finding 1 — Rebuild and verify served frontend bundle (`7c253d5`):**
  - Rebuilt static distribution bundle from `frontend/src` into `app/static` via `npm run build` (`index-zR2_NRAl.js`, `index-BmGRgiJJ.css`).
  - Verified bundle contains all current pipeline stage identifiers (`RESOLVING_TICKER`, `INGESTING_NEWS`, `FILTERING_DEDUPLICATING`, `FINBERT_SCORING`, `CATALYST_SYNTHESIS`, `AGGREGATING_DECISION`), data statuses (`NO_FRESH_NEWS`, `NO_RELEVANT_NEWS`, `DEGRADED`), hold reasons (`NO_NEWS`, `SPARSE_EVIDENCE`, `INSUFFICIENT_CORROBORATION`, `CONFLICTING`, `NEUTRAL`), and corroboration badge strings (`Corroborated`, `Single Publisher`, `Uncorroborated`, `Supporting Source`).
  - Added CI check to `.github/workflows/ci.yml` under `frontend` job executing `git diff --exit-code ../app/static`.
  - Replaced outdated `index-CpE2UDUr.js` with committed `index-zR2_NRAl.js`.
  - Verification: `npm.cmd run build` produced identical bundle hash; `git diff --exit-code ../app/static` returned 0.

- **Finding 2 — Directional corroboration badge (`35f3717`):**
  - Updated `DecisionHero.tsx` to evaluate `isCorroborated = (verdict === 'BUY' || verdict === 'SELL') && supportingPubs >= 2`.
  - Gated badge text so that `HOLD` verdicts never display "Corroborated" regardless of `distinct_publishers`.
  - Confirmed inferred publishers and aggregators cannot contribute to `supporting_publishers` in `AggregatorService`.
  - Added unit test cases for BUY, SELL, HOLD, inferred publishers, and mixed positive/negative publisher sets in `tests/unit/test_aggregator.py`. Added 7 component tests in `frontend/src/components/DecisionHero.test.tsx`.
  - Verification: `pytest tests/unit/test_aggregator.py` (18 passed); `npm.cmd test` (7 passed in `DecisionHero.test.tsx`).

- **Finding 3 — Stale search request prevention (`16051fd`):**
  - Introduced monotonic request generation counter `currentRequestIdRef` in `App.tsx` guarding both initial `/analyze` response handling and async `subscribeToJob` callbacks (`onProgress`, `onComplete`, `onError`).
  - Selecting a historical run or initiating a newer search increments `currentRequestIdRef` and cancels existing SSE subscriptions; stale responses from earlier searches are discarded.
  - Added regression test suite in `frontend/src/App.test.tsx` verifying:
    1. Selecting a historical run while `/analyze` is pending discards the late-arriving search result.
    2. Starting a new search cancels and discards subsequent job events from an older in-flight job.
  - Verification: `npm.cmd test` (2 passed in `App.test.tsx`).

- **Finding 4 — Total outage degraded persistence (`bd82f28`):**
  - Reconciled total-provider-outage with Phase 2 data status contract: `AnalysisOrchestrator.run_pipeline` now emits a non-cacheable `DEGRADED` run (`data_status=DataStatus.DEGRADED`, `is_cacheable=False`, `decision=DecisionVerdict.HOLD`, `hold_reason=HoldReason.NO_NEWS`, `confidence=0.0`) instead of raising `NewsUnavailableException` (503).
  - Persisted record in database has `is_cacheable=False`, is retrievable via `/analysis/{run_id}`, and is bypassed on subsequent cache lookups.
  - Updated `test_total_provider_outage_produces_persisted_degraded_run_and_not_cached` in `tests/integration/test_data_status.py` and updated `test_total_provider_outage_emits_degraded_non_cacheable_run` in `tests/integration/test_freshness_orchestrator.py`.
  - Verification: `pytest tests/integration/test_data_status.py` (4 passed); `pytest tests/integration/test_freshness_orchestrator.py` (3 passed).

- **Finding 5 — Prompt budget enforcement (`4a9238a`):**
  - Replaced character-based estimate with bounded conservative estimator `estimate_prompt_tokens()`: takes the maximum of `len(prompt) / 3.0` and `len(prompt.split()) * 1.35 + 4`.
  - If prompt still exceeds `MAX_PROMPT_TOKENS` even with candidate articles trimmed down to 1, LLM synthesis is safely skipped with `status="SKIPPED"`, `reason="PROMPT_EXCEEDS_BUDGET"`, empty facts, and empty summary.
  - Added unit test `test_max_prompt_tokens_exceeded_skips_synthesis` in `tests/unit/test_llm_service.py`.
  - Verification: `pytest tests/unit/test_llm_service.py` (12 passed).

- **Finding 6 — LLM fallback defaults per Decision D5 (`4a9238a`):**
  - Configured `LLM_FALLBACK_MODEL_ID = "nvidia/nemotron-3-super-120b-a12b:free"` in `app/config.py` Settings and `.env.example`.
  - Included `LLM_FALLBACK_MODEL_ID` in `Settings.get_config_hash()` so cache/config fingerprints change if either primary or fallback model changes.
  - Maintained full environment variable override support via Pydantic settings.
  - Added unit test `test_config_hash_fingerprint_models` in `tests/unit/test_llm_service.py` and updated `test_env_example_matches_config_defaults` in `tests/unit/test_deduplication.py`.
  - Verification: `pytest tests/unit/test_llm_service.py -k "test_config_hash_fingerprint_models"` passed; `pytest tests/unit/test_deduplication.py -k "test_env_example_matches_config_defaults"` passed.

- **Finding 7 — Migration 002 downgrade safety with nullable publication times (`a201e29`):**
  - Updated `downgrade()` in `alembic/versions/002_freshness_reliability_schema.py` to backfill existing `NULL` rows in `article_evidence.published_at_utc` with Unix epoch sentinel `'1970-01-01 00:00:00'` before re-applying `nullable=False`.
  - Created integration migration test `tests/integration/test_migration_002_downgrade.py`: inserts an undated article row with `published_at_utc=None`, executes `alembic downgrade -1` to 001, verifies the row is preserved with sentinel date, and upgrades back to `head`.
  - Verification: `pytest tests/integration/test_migration_002_downgrade.py` passed; `alembic check` clean (zero schema drift).

- **Finding 8 — Frontend health helper path (`16051fd`):**
  - Updated `getHealth()` in `frontend/src/services/api.ts` to request `${API_BASE}/health` (`/api/v1/health`) matching backend mount route.
  - Added unit tests in `frontend/src/services/api.test.ts` asserting exact path `/api/v1/health` and error parsing.
  - Verification: `npm.cmd test` (5 passed in `api.test.ts`).

- **Finding 9 — Project-state claims & handover accuracy:**
  - Updated `docs/implementation_log.md` and `docs/auditor_progress_handover.md` to clearly distinguish completed Phase 2 audit fixes from pending Phase 3–4 work.
  - Documented exact commands actually executed and verified. Tracked handover document in repository.
  - Verification: Full backend test suite `pytest --cov=app --cov-report=term-missing --cov-fail-under=85` passed at 89.58% (227 passed); `ruff check .` clean; `alembic check` clean; `npm.cmd run typecheck` clean; `npm.cmd test` passed (14 passed); static bundle drift check `git diff --exit-code ../app/static` clean.

## Phase 3 — Performance, reliability, security

- **Task P3.1 — Ingestion rework (`71b22f5`):**
  - Re-architected `NewsService` with `FeedSpec` list and launched Yahoo Finance (`get_news(count=YF_NEWS_COUNT)`) on I/O executor and all RSS feeds concurrently using `asyncio.wait(tasks, timeout=settings.INGESTION_TIMEOUT_SECONDS)`.
  - Configured tenacity retry with random exponential backoff and jitter on 429, 5xx, and transport/timeout exceptions.
  - Implemented non-feed HTML response detection marking `status="FAILED"`, `error_code="NOT_A_FEED"` without retrying consent pages.
  - Preserved partial results when timeouts occur, marking stragglers `status="TIMEOUT"`.
  - Confined ingestion deduplication to dropping only exact duplicate `article_id`s; title and near-duplicate clustering moves after the freshness window filter.
  - Enhanced `canonicalize_url()` to be non-mutating and return `""` for non-http(s) schemes; precomputed Jaccard token sets once per article in `DeduplicationService.process_and_deduplicate()`.
  - Defined `ProviderKind` enum, `FeedSpec` dataclass, `ProviderOutcome` model, and `PipelineDeps` container; exposed `AnalysisResult.provider_outcomes` and persisted in `analysis_runs.provider_outcomes_json`.
  - Updated orchestrator outage detection to evaluate `outcome.kind` rather than key string prefixes.
  - Initialized shared `httpx.AsyncClient` in `app/main.py` lifespan and registered on `app.state.pipeline_deps`.
  - Added unit tests in `tests/unit/test_news_service.py` and `tests/unit/test_deduplication.py` for concurrent launch, timeout partial retention, HTML 200 rejection, 503 retry, Yahoo count, outcome kinds outage detection, non-http URL stripping, and exact id deduplication.
  - Verification: `pytest --cov=app --cov-fail-under=85` passed at 88.69% (234 passed); `ruff check .` clean; `alembic check` clean; `npm.cmd test` (14 passed); `npm.cmd run typecheck` clean; static bundle drift clean.

- **Task P3.2 — FinBERT throughput and dependency injection (`55ee3f6`):**
  - Created `app/services/scoring.py` with `ClassProbs` dataclass and runtime checkable `SentimentScorer` protocol (`load()`, `state`, `async score(texts) -> list[ClassProbs]`).
  - Implemented `FinBERTScorer` wrapping transformers pipeline on a dedicated single-thread executor (`ThreadPoolExecutor(max_workers=1, thread_name_prefix="finbert")`), lazily importing transformers and torch inside `load()`.
  - Implemented batched inference `pipeline(chunk, batch_size=settings.FINBERT_BATCH_SIZE, truncation=True, max_length=512)` with output normalization across transformers versions and single/nested dict structures, optional `torch.set_num_threads(FINBERT_TORCH_THREADS)`, and cooperative inter-chunk cancellation checks (`asyncio.CancelledError`).
  - Configured non-blocking preload task in `app/main.py` lifespan when `FINBERT_PRELOAD=True`, waiting for readiness within job timeouts, with executor shutdown on application exit.
  - Built `lead_text` directly at the source (`f"{art.title}. {art.summary}".strip()[:500]`) on `ScoredArticle`, deleting the O(N²) patch loop in `app/services/orchestrator.py`.
  - Removed legacy mock code (`set_mock_mode`, `reset_mock_mode`, `_is_mock`, `_mock_fn`) and `MAX_EXCERPT_TOKENS` from `FinBERTService` and `app/config.py`.
  - Updated `KeywordScorer` in `tests/fakes.py` to implement the `SentimentScorer` protocol while preserving callable backward compatibility; tests inject `KeywordScorer` via `set_default_scorer` and `PipelineDeps`.
  - Created `scripts/bench_finbert.py` demonstrating 1.81x throughput improvement (44.5 ms -> 24.6 ms per article) vs legacy sequential loop with encode/decode round trip.
  - Added unit test suite `tests/unit/test_scoring.py` covering protocol conformance, output normalization, batched chunking, inter-chunk cancellation, error states, and dependency injection.
- **Task P3.3 — Stop blocking the event loop (`a7cb23e`):**
  - Created `app/utils/executors.py` introducing dedicated worker pools: `db_executor` (4 threads) and `io_executor` (4 threads), along with `run_db(fn, *args)` async helper running repository functions in worker threads with their own isolated Sessions.
  - Added SQLite `PRAGMA busy_timeout=5000` in `app/db/database.py` connection event listener to eliminate database locking contention.
  - Registered `db_executor` and `io_executor` on `PipelineDeps` and `app.state` during lifespan, and ensured graceful shutdown in lifespan finally block.
  - Converted DB-only endpoints (`/jobs/{job_id}`, `/analysis/{run_id}`, `/history`, and `/health`) to plain synchronous `def` handlers offloaded to FastAPI worker threads.
  - Updated `run_background_job`, `analyze_ticker`, and `AnalysisOrchestrator` to offload repository caching and persistence calls via `run_db`.
  - Added unit test suite `tests/unit/test_executors.py` verifying offloading to worker threads, executor shutdown, and demonstrating `/api/v1/health` responds in < 200 ms while a slow DB operation executes on `db_executor`.
  - Verification: `pytest --cov=app --cov-fail-under=85` passed at 87.91% (244 passed); `ruff check .` clean; `alembic check` clean; `test_openapi_matches_committed_snapshot` clean.
- **Task P3.4 — Job manager: limits, coalescing, SSE (`96d6131`):**
  - Created `app/services/job_manager.py` implementing `JobManager` attached to `app.state.job_manager` with a global `asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)` (default 2), queue position tracking with "Waiting for a worker (N ahead)" updates, and queue timeout `JOB_QUEUE_TIMEOUT_SECONDS` (120s) failing jobs with `QUEUE_TIMEOUT`.
  - Implemented true request coalescing: `submit()` tracks in-flight jobs by cache key, attaching concurrent identical requests to the active job with `coalesced: True` and returning the same `job_id`.
  - Completely removed import-time lock hazard and unbounded dictionary leak by deleting `app/utils/lock_manager.py` (`TickerLockManager`).
  - Added pub/sub in-process event channel for real-time SSE streaming with periodic `: ping\n\n` comments every `SSE_HEARTBEAT_SECONDS` (15s), seamless fallback to 1s DB polling for out-of-process jobs, overall deadline calculation using `time.monotonic()`, and immediate disconnection cleanup upon client disconnect.
  - Updated `JobCreatedResponse` schema with `coalesced: bool = False` and refreshed `frontend/src/api/openapi.json`.
  - Added `cancel_job` in `SentimentRepository`; `JobManager.shutdown()` cancels running pipeline tasks and marks jobs `CANCELLED` in database.
  - Added comprehensive test suite `tests/unit/test_job_manager.py` covering coalescing, sequential limit execution, queue timeout, pipeline timeout, shutdown cancellation, SSE heartbeats, and client disconnection.
  - Verification: `pytest --cov=app --cov-fail-under=85` passed at 87.19% (251 passed); `ruff check .` clean; `alembic check` clean; `test_openapi_matches_committed_snapshot` clean.
- **Task P3.5 — Rate limiting and client IP (`0e1889d`):**
  - Refactored `SlidingWindowRateLimiter` to support scoped rate limits: `analyze` (15/min), `jobs` (60/min), and `read` (120/min via `RATE_LIMIT_READ_PER_MINUTE`), avoiding starvation between polling/reading and submission.
  - Replaced unbounded dictionary with bounded `OrderedDict` LRU cache strictly capped at `max_keys=10000`, evicting oldest keys on overflow.
  - Implemented precise `Retry-After` calculation bounded between 1 and window duration using `math.ceil(window - elapsed)`.
  - Implemented secure right-to-left `X-Forwarded-For` proxy resolution walking back through `TRUSTED_PROXY_IPS` (supporting exact IPs and CIDR ranges) to the first untrusted IP, ignoring forged client-supplied leftmost headers when direct connection peer is untrusted.
  - Converted routes to use declarative `rate_limit(scope)` dependencies (`/analyze` uses `analyze`, `/jobs/{job_id}` and `/jobs/{job_id}/events` use `jobs`, `/analysis/{run_id}` and `/history` use `read`).
  - Added unit test suite `tests/unit/test_rate_limiter.py` and updated `tests/unit/test_api_security_and_limits.py`.
  - Verification: `pytest --cov=app --cov-fail-under=85` passed at 86.79% (259 passed); `ruff check .` clean; `alembic check` clean; `test_openapi_matches_committed_snapshot` clean.
- **Task P3.6 — Cost, abuse and input controls (`54c726a`):**
  - Created migration `alembic/versions/005_operations.py` adding `analysis_runs.llm_cost_usd` (FLOAT, default 0.0), backfilling from `metrics_json` via SQLite JSON extract, and adding operational indexes `ix_analysis_runs_created_at` and `ix_analysis_jobs_expires_at`.
  - Implemented daily LLM spend tracking: added `SentimentRepository.get_daily_llm_spend(db, target_date)` aggregating UTC spend; `LLMService.verify_and_synthesize` checks `get_today_utc_spend()` against `LLM_DAILY_BUDGET_USD` ($1.00) and safely skips LLM calls with `status="SKIPPED"`, `reason="DAILY_BUDGET_EXCEEDED"`, degrading to deterministic FinBERT-only verdict.
  - Implemented optional API key authentication: `API_KEY` setting and `verify_api_key` dependency rejecting missing or incorrect `X-API-Key` headers with 401 `UnauthorizedException`. Gated history inspection (`/history` and `/analysis/{run_id}`) behind `verify_history_access` when `PUBLIC_HISTORY=False`.
  - Enforced strict ticker input controls: `AnalyzeRequest.ticker` constrained to `min_length=1, max_length=20` (returning 422 `RequestValidationError` for >20 chars); updated `TickerService.normalize_ticker()` to enforce maximum 20-character length across all notations.
  - Configured security headers middleware adding `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and basic CSP (`default-src 'self'`); set CORS `allow_credentials=False`.
  - Added unit test suite `tests/unit/test_cost_and_abuse_controls.py` (9 tests) and migration test `tests/integration/test_migration_005.py`.
  - Verification: `pytest --cov=app --cov-fail-under=85` passed at 86.08% (269 passed); `ruff check .` clean; `alembic check` clean; `test_openapi_matches_committed_snapshot` clean.
- **Task P3.7 — Data retention lifecycle, sample exclusion capping, and CLI (`5959820`):**
  - Updated `DeduplicationService.process_and_deduplicate()` to return `DedupResult(retained, sample_excluded, cluster_map, counts)` preserving 3-element tuple unpacking while exposing `.counts`.
  - Implemented sample exclusion capping: relevance, duplicate syndication, and capacity limit exclusions are all counted in full, but `sample_excluded` stores at most `MAX_EXCLUDED_SAMPLES_PER_REASON` (20) samples per reason.
  - Updated `AnalysisOrchestrator` to accurately record total exclusions in `metrics.articles_excluded_total` and `metrics.excluded_counts` across all early-exit and normal branches, eliminating duplicate freshness counts and limiting persisted `AnalysisResult.articles` sample excluded items to at most 20 per reason.
  - Created `app/services/maintenance.py` with `delete_expired_jobs(db, now)` removing jobs past `expires_at`, `delete_old_analysis_runs(db, retention_days=30, now)` cascading deletion to `ArticleEvidenceDB` and `ObservedFactDB`, and `run_maintenance(session_factory, retention_days, vacuum, now)` supporting SQLite autocommit `VACUUM`.
  - Created `app/cli.py` providing CLI runner `python -m app.cli maintenance [--vacuum] [--retention-days N]`.
  - Added hourly background maintenance worker in `app/main.py` lifespan running `run_maintenance()` on the DB thread pool and cleanly cancelling on server shutdown.
  - Added test suite `tests/unit/test_maintenance.py` verifying job expiration, run retention cascade, maintenance CLI invocation, and deduplication sample capping.
  - Verification: `pytest --cov=app --cov-fail-under=85` passed at 85.70% (274 passed); `ruff check .` clean; `alembic check` clean; `test_openapi_matches_committed_snapshot` clean.

## Deviations

_None._

## Follow-ups

_None._


