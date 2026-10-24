# Project Audit & Progress Handover Document

**Project:** Market Sentiment 2 (SentimentPulse Remediation)  
**Target Audience:** Auditor Agent / Quality Assurance Reviewer  
**Governing Plan:** [docs/implementation_plan.md](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md) (Approved 2026-10-19; Decisions [D1–D8](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L42-L57))  
**Remediation Audit Log:** [docs/implementation_log.md](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_log.md)  
**Baseline Reference:** `main` @ `cab8b54` (Remediating 49 findings: [C1–C4, H1–H17, M1–M18, L1–L10](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L27))  
**Current Active Branch:** `fix/phase-2-decision-integrity`  
**Current Working Tree:** Clean (all files tracked and verified, including this handover document)  

---

## 1. Executive Summary & Verification Gates

The project is executing a 5-phase architectural and algorithmic remediation to eliminate reliability hazards, silent data corruption, false confidence inflation, and contract drift. Following the initial completion of Phase 2, a 9-point auditor review was conducted and all findings have been fully remediated and verified on this branch.

### Current Project Health & Measured Quality Gates

| Quality Gate | Requirement | Current Measured State | Status |
|---|---|---|---|
| **Backend Test Suite** | 100% offline pass | **227 passed**, 4 deselected (opt-in markers) in ~9.8s | **PASS** |
| **Backend Code Coverage** | $\ge 85\%$ strict enforcement | **89.58%** overall backend coverage | **PASS** |
| **Lint & Formatting** | `ruff check .` clean | 0 errors, 0 warnings across whole repo | **PASS** |
| **Database Schema Drift** | `alembic check` zero drift | Current revision `004_decision_integrity` aligned with ORM | **PASS** |
| **Contract Alignment** | OpenAPI snapshot equality | [tests/contract/test_openapi_snapshot.py](file:///d:/Code%20Projects/Market%20Sentiment%202/tests/contract/test_openapi_snapshot.py) clean | **PASS** |
| **Frontend Typecheck** | `tsc --noEmit` clean | 0 type errors across frontend and tests | **PASS** |
| **Frontend Test Suite** | 100% Vitest pass | **14 passed** across 3 test files in ~1.8s | **PASS** |
| **Static Bundle Drift** | Build matches committed assets | `git diff --exit-code ../app/static` clean (0 diff) | **PASS** |

---

## 2. Work Completed by the Preceding Agent

The preceding agent completed **Phase 0 (Safety Net)**, **Phase 1 (User Flow & Persistence)**, and the first four tasks of **Phase 2 (Decision Integrity)** across branches `fix/phase-0-safety-net`, `fix/phase-1-user-flow`, and `fix/phase-2-decision-integrity`.

### Phase 0: Safety Net
*Tracked in [docs/implementation_plan.md §4](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L84-L140) and [docs/implementation_log.md §Phase 0](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_log.md#L47-L87)*

- **P0.1 Isolated, Deterministic, Offline Test Suite ([`d061051`](file:///d:/Code%20Projects/Market%20Sentiment%202/tests/conftest.py)) — Findings: H1, H17**
  - Isolated SQLite DB created in temp dir; network guard monkeypatches `socket` and stubs Yahoo Finance; time-freezing fixture `frozen_now` using `time-machine`.
  - Added strict Pydantic parsing (`extra="forbid"`) to [IngestedArticle](file:///d:/Code%20Projects/Market%20Sentiment%202/app/core/models.py) and [ScoredArticle](file:///d:/Code%20Projects/Market%20Sentiment%202/app/core/models.py).
- **P0.2 Clean Polluted Local Database — Findings: H1, Decision: D7**
  - Checkpointed WAL, backed up `data/sentiment.db` to `sentiment.db.bak-20261019`, and purged 10 leftover fixture runs.
- **P0.3 Application Logger Preservation ([`4221c23`](file:///d:/Code%20Projects/Market%20Sentiment%202/alembic/env.py)) — Finding: H2**
  - Prevented Alembic migrations from silencing application loggers; introduced `LOG_LEVEL` setting.
- **P0.4 Tooling, Dependency Pinning & CI ([`400fccd`](file:///d:/Code%20Projects/Market%20Sentiment%202/pyproject.toml)) — Findings: M17, L7, L9**
  - Pinned `requirements.txt` and `requirements-dev.txt`; added `pyproject.toml` (Ruff) and `.github/workflows/ci.yml`.

### Phase 1: User-Facing Flow & Persistence
*Tracked in [docs/implementation_plan.md §5](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L141-L260) and [docs/implementation_log.md §Phase 1](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_log.md#L88-L128)*

- **P1.1 Typed SSE Contract & OpenAPI Snapshot ([`3699230`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/api/schemas.py)) — Finding: C1**
  - Added typed SSE events ([JobProgressEvent](file:///d:/Code%20Projects/Market%20Sentiment%202/app/api/schemas.py), [JobCompletedEvent](file:///d:/Code%20Projects/Market%20Sentiment%202/app/api/schemas.py), [JobFailedEvent](file:///d:/Code%20Projects/Market%20Sentiment%202/app/api/schemas.py)) and [scripts/export_openapi.py](file:///d:/Code%20Projects/Market%20Sentiment%202/scripts/export_openapi.py).
- **P1.2 Robust Frontend Job Client ([`633e478`](file:///d:/Code%20Projects/Market%20Sentiment%202/frontend/src/services/api.ts)) — Findings: C1, M6**
  - Frontend client cancellation tokens, backoff polling fallback (1s doubling to 5s), and server-communicated deadlines.
- **P1.3 & P1.4 Database Persistence Integrity ([`18aaf9e`](file:///d:/Code%20Projects/Market%20Sentiment%202/alembic/versions/003_persistence_integrity.py)) — Findings: C2, H13, L3, L4, M14**
  - Migration `003`: added `analysis_runs.is_cacheable`, widened `ticker` to `VARCHAR(32)`, enforced unique `(run_id, article_id)`.
- **P1.5 Timezone-Aware Datetimes ([`09bcb77`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/db/types.py)) — Findings: M2, M14**
  - Created [UTCDateTime](file:///d:/Code%20Projects/Market%20Sentiment%202/app/db/types.py) `TypeDecorator` ensuring all timestamps are timezone-aware UTC and serialized with trailing `Z`.
- **P1.6 Truthful UI Telemetry ([`b5fd751`](file:///d:/Code%20Projects/Market%20Sentiment%202/frontend/src/components/EvidenceExplorer.tsx)) — Findings: M1–M5, M10**
  - Telemetry breakdown for exclusions, directional threshold filtering, and LLM catalyst synthesis cards.
- **P1.7 Unified Error Handling & Health ([`3eeb71f`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/main.py)) — Finding: M9**
  - Unified JSON error handlers and honest `/health` endpoint reflecting real [FinBERTService](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/finbert_service.py) states.
- **P1.8 & P1.9 Hotfixes & Bundle Validation ([`793e3ee`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/news_service.py)) — Findings: H10, L2, Decision: D4**
  - Null-safe yfinance payload parsing and keyword-bound [FreshnessViolationException](file:///d:/Code%20Projects/Market%20Sentiment%202/app/core/exceptions.py).

### Phase 2: Decision Integrity (Initial Tasks)
*Tracked in [docs/implementation_plan.md §6](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L261-L380) and [docs/implementation_log.md §Phase 2](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_log.md#L129-L154)*

- **P2.1 Directional Corroboration ([`6126557`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/aggregator_service.py)) — Findings: C4, M11, M3**
  - Migration `004_decision_integrity.py` adding `article_evidence.publisher_inferred` and `analysis_runs.hold_reason`.
  - Directional corroboration logic: BUY requires distinct positive publishers $P_{\text{pos}} \ge 2$; SELL requires $P_{\text{neg}} \ge 2$. Inferred publishers and aggregators are excluded.
- **P2.2 Relevance Engine Rebuild ([`336b038`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/relevance.py)) — Findings: C3, H4, M15**
  - Multi-asset relevance engine in [relevance.py](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/relevance.py) and [asset_registry.py](file:///d:/Code%20Projects/Market%20Sentiment%202/app/core/asset_registry.py) covering Equities, Forex, Commodities, and Futures.
  - Validated against 65 table-driven test cases in [tests/fixtures/relevance_cases.json](file:///d:/Code%20Projects/Market%20Sentiment%202/tests/fixtures/relevance_cases.json).
- **P2.3 Ticker Resolution Engine ([`5c2507e`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/ticker_service.py)) — Findings: H3, H5, M16**
  - Caching keyed by `(normalized, bypass_aliases)` with 6h TTL, 10m negative cache, futures mapping (`ES=F` -> `FUTURES`), and pre-resolved [Asset](file:///d:/Code%20Projects/Market%20Sentiment%202/app/core/models.py) passing to eliminate `$` loss.
- **P2.4 Session Window & Market Calendar ([`d745273`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/core/market_calendar.py)) — Findings: H14, L5, M13, Decision: D1**
  - Explicit calendar for 2025–2027 NYSE holidays/early closes. Unified rule: starts at prior active day close (16:00/13:00 ET), capped at 72h.

---

## 3. Work Completed by the Current Agent (Finishing Phase 2 & Audit Remediation)

The current agent completed tasks P2.5–P2.7 and addressed all 9 audit review findings on branch `fix/phase-2-decision-integrity`.

### Initial Phase 2 Tasks
- **P2.5 LLM Robustness & Multi-Model Fallback ([`7b9a8e1`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/llm_service.py)):**
  - Configured shared `AsyncOpenAI` client lifecycle in lifespan.
  - Multi-model fallback loop bounded by 30s deadline, degrading to deterministic mode rather than failing the job.
  - Prompt hardening: XML entity escaping order, control character stripping, bounded headlines and publishers.
- **P2.6 Data Status, HOLD Reasons, and Confidence Ceilings ([`e933e73`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/orchestrator.py)):**
  - Enforced `DataStatus` lifecycle (`OK`, `NO_FRESH_NEWS`, `NO_RELEVANT_NEWS`, `DEGRADED`).
  - Stored `HoldReason` and applied Decision D6 confidence ceilings ($0.0$ for evidence-free HOLDs, $0.95$ hybrid ceiling gated on directional catalyst verification, $0.60$ baseline).
- **P2.7 Phase 2 Documentation ([`b9494e6`](file:///d:/Code%20Projects/Market%20Sentiment%202/README.md)):**
  - Updated `README.md` and logged initial Phase 2 completion.

### Auditor Findings Remediation (2026-10-24)
- **Finding 1 — Rebuild and verify served frontend bundle ([`7c253d5`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/static/assets/index-zR2_NRAl.js)):**
  - Rebuilt static distribution bundle from `frontend/src` into `app/static` (`index-zR2_NRAl.js`, `index-BmGRgiJJ.css`).
  - Confirmed generated bundle contains current backend stage names (`RESOLVING_TICKER`, `INGESTING_NEWS`, `FILTERING_DEDUPLICATING`, `FINBERT_SCORING`, `CATALYST_SYNTHESIS`, `AGGREGATING_DECISION`), data statuses (`NO_FRESH_NEWS`, `NO_RELEVANT_NEWS`, `DEGRADED`), hold reasons (`NO_NEWS`, `SPARSE_EVIDENCE`, `INSUFFICIENT_CORROBORATION`, `CONFLICTING`, `NEUTRAL`), and corroboration UI (`Corroborated`, `Single Publisher`, `Uncorroborated`, `Supporting Source`).
  - Added CI check to `.github/workflows/ci.yml` failing if `app/static` differs from committed bundle (`git diff --exit-code ../app/static`).
- **Finding 2 — Directional corroboration badge ([`35f3717`](file:///d:/Code%20Projects/Market%20Sentiment%202/frontend/src/components/DecisionHero.tsx)):**
  - Updated `DecisionHero.tsx` so badge reflects directional `supporting_publishers >= 2` for BUY/SELL; HOLD verdicts never display "Corroborated".
  - Inferred publishers and aggregators strictly excluded from corroboration metrics in `AggregatorService`.
  - Added comprehensive test coverage in `tests/unit/test_aggregator.py` and `frontend/src/components/DecisionHero.test.tsx`.
- **Finding 3 — Stale search request prevention ([`16051fd`](file:///d:/Code%20Projects/Market%20Sentiment%202/frontend/src/App.tsx)):**
  - Introduced monotonic request generation counter `currentRequestIdRef` in `App.tsx` covering initial `/analyze` response and async job subscription callbacks.
  - Stale responses or job events from earlier searches are discarded when user selects history or starts a newer search.
  - Added regression test suite in `frontend/src/App.test.tsx` testing history selection while `/analyze` is pending and superseding active jobs.
- **Finding 4 — Total outage degraded persistence ([`bd82f28`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/orchestrator.py)):**
  - Reconciled total-provider-outage with Phase 2 data status contract: emits non-cacheable `DEGRADED` run with `decision=HOLD`, `hold_reason=NO_NEWS`, `confidence=0.0` instead of raising 503.
  - Persisted record in database has `is_cacheable=False`, is retrievable via `/analysis/{run_id}`, and is bypassed on subsequent cache lookups.
  - Added tests in `tests/integration/test_data_status.py` and `tests/integration/test_freshness_orchestrator.py`.
- **Finding 5 — Prompt budget enforcement ([`4a9238a`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/llm_service.py)):**
  - Replaced character-based estimate with bounded conservative estimator `estimate_prompt_tokens()`.
  - Safely skips LLM synthesis with `status="SKIPPED"` and `reason="PROMPT_EXCEEDS_BUDGET"` when prompt exceeds `MAX_PROMPT_TOKENS` even with 1 candidate remaining.
  - Added unit test `test_max_prompt_tokens_exceeded_skips_synthesis` in `tests/unit/test_llm_service.py`.
- **Finding 6 — LLM fallback defaults per Decision D5 ([`4a9238a`](file:///d:/Code%20Projects/Market%20Sentiment%202/app/config.py)):**
  - Set approved fallback model `nvidia/nemotron-3-super-120b-a12b:free` as default in `Settings` and `.env.example`.
  - Included fallback model in `Settings.get_config_hash()`. Tested in `tests/unit/test_llm_service.py` and `tests/unit/test_deduplication.py`.
- **Finding 7 — Migration 002 downgrade safety ([`a201e29`](file:///d:/Code%20Projects/Market%20Sentiment%202/alembic/versions/002_freshness_reliability_schema.py)):**
  - Backfilled null `published_at_utc` rows with epoch sentinel `'1970-01-01 00:00:00'` during downgrade before re-applying `nullable=False`.
  - Added migration integration test in `tests/integration/test_migration_002_downgrade.py`.
- **Finding 8 — Frontend health helper path ([`16051fd`](file:///d:/Code%20Projects/Market%20Sentiment%202/frontend/src/services/api.ts)):**
  - Updated `getHealth()` to request `${API_BASE}/health` (`/api/v1/health`).
  - Added focused contract unit tests in `frontend/src/services/api.test.ts`.
- **Finding 9 — Project-state claims:**
  - Accurately logged all remediation items in `docs/implementation_log.md` and tracked this handover document.

---

## 4. What Remains to Be Done (Phases 3 and 4)

Phases 0 through 2 (and the audit remediation plan) are **100% complete**. The following work is pending in future phases on their respective planned branches:

### Phase 3: Performance, Reliability, Security
*Branch to create: `fix/phase-3-performance-reliability` | Detailed in [docs/implementation_plan.md §7](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L402-L493)*

1. **P3.1 Ingestion Rework (Findings: H9, M15, M10, L10):**
   - Single shared `httpx.AsyncClient` in lifespan with connection pooling and `HTTP_USER_AGENT`.
   - Concurrent launch of Yahoo Finance and all RSS feeds with `asyncio.wait(..., timeout=INGESTION_TIMEOUT_SECONDS)`.
   - Feed retry with jitter (tenacity); detect HTML non-feed responses as `FAILED("NOT_A_FEED")`.
   - Non-mutating `canonicalize_url()` in [news_service.py](file:///d:/Code%20Projects/Market%20Sentiment%202/app/services/news_service.py); provider outcomes exposed in `AnalysisResult`.
2. **P3.2 FinBERT Throughput & Dependency Injection (Findings: H8, M16):**
   - Dedicated single-thread executor with batched chunk inference (`pipeline(..., batch_size=16)`).
   - Non-blocking preload during lifespan (`FINBERT_PRELOAD=true`).
   - Remove legacy mock code; inject `SentimentScorer` protocol via `PipelineDeps`.
3. **P3.3 Stop Blocking the Event Loop (Finding: H11):**
   - Dedicated `db_executor` (4 threads) and `io_executor` (4 threads); SQLite `PRAGMA busy_timeout=5000`.
   - `await run_db(fn, *args)` helper for all repository interactions.
4. **P3.4 Job Manager, Concurrency Limits & Request Coalescing (Findings: M7, M8, H15, L6):**
   - New `JobManager` with `asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)` (default 2), queue timeouts, in-flight coalescing by cache key, and SSE heartbeats.
5. **P3.5 Rate Limiting & Proxy IP Resolution (Finding: H12):**
   - Scoped rate limiter (`analyze` 15/min, `jobs` 60/min, `read` 120/min) with bounded LRU key store.
   - Right-to-left `X-Forwarded-For` proxy walking against `TRUSTED_PROXY_IPS`.
6. **P3.6 Cost, Abuse & Input Controls (Findings: H15, L3, L10, Decision: D2):**
   - Migration `005_operations.py` adding `analysis_runs.llm_cost_usd`.
   - Spend tracking against `LLM_DAILY_BUDGET_USD` ($1.00); optional `API_KEY` guard for `/analyze` and private history.
7. **P3.7 Data Lifecycle & Retention (Finding: H16):**
   - Lifespan retention task purging jobs past `expires_at` and runs older than `RUN_RETENTION_DAYS` (30).
   - `python -m app.cli maintenance` script.
8. **P3.8 Configuration & Startup (Findings: M13, L7, Decision: D3):**
   - Package-anchored path resolution for `.env` and SQLite DB; full `.env.example` alignment test.
   - Startup warning for timeout misconfigurations.

### Phase 4: Code Quality & Documentation
*Branch to create: `fix/phase-4-code-quality` | Detailed in [docs/implementation_plan.md §8](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md#L495-L535)*

1. **P4.1 Orchestrator Refactor (Finding: M16):**
   - Decompose `run_pipeline` into discrete stage methods over a `PipelineContext`. Golden-snapshot test to guard against behavioral drift.
2. **P4.2 Dead Code & Lint (Finding: L1):**
   - Remove unused exceptions, enums (`FINNHUB`, `INDEX`), and dead models. Tighten Ruff rules.
3. **P4.3 Documentation & Versioning (Finding: M18):**
   - Archive legacy `IMPLEMENTATION_PLAN.md` to `docs/history/`; create `CHANGELOG.md` for v1.1.0; bump version numbers.
4. **P4.4 Frontend Quality (Finding: L8):**
   - Bundle self-hosted fonts; enforce strict TypeScript typing.
5. **P4.5 Repository Hygiene (Finding: L9):**
   - Add `.gitattributes` for LF/CRLF normalization; ensure `.gitignore` guards all test artifacts.
6. **P4.6 Persistence Details (Finding: L4):**
   - Audit cascade deletion constraints across all SQLite relationships.

---

## 5. Auditor Verification Instructions

To independently verify the integrity of the repository and confirm that Phase 2 and all audit findings remediation were completed properly, run the following commands:

### Backend Checks
```powershell
# 1. Lint & Static Analysis
ruff check .

# 2. Comprehensive Backend Test Suite & Code Coverage
pytest --cov=app --cov-report=term-missing --cov-fail-under=85

# 3. Database Schema & Migration Drift
alembic check

# 4. Migration 002 Downgrade Safety Test
pytest tests/integration/test_migration_002_downgrade.py -v

# 5. OpenAPI Contract Snapshot Check
pytest tests/contract/test_openapi_snapshot.py -v
```

### Frontend Checks
```powershell
# Set Node and npm in environment PATH (if needed)
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
cd frontend

# 6. TypeScript Typecheck
npm.cmd run typecheck

# 7. Frontend Unit and Regression Tests
npm.cmd test

# 8. Rebuild Static Distribution Bundle
npm.cmd run build

# 9. Verify Static Bundle Matches Committed Assets (Bundle Drift Check)
git diff --exit-code ../app/static
```

---

## 6. Audit Verdict & Recommendation

- **Direction Assessment:** The implementation strictly adheres to the approved architectural blueprint in [docs/implementation_plan.md](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_plan.md), addresses all 9 audit findings, and accurately records progress in [docs/implementation_log.md](file:///d:/Code%20Projects/Market%20Sentiment%202/docs/implementation_log.md).
- **Integrity Assessment:** Zero regressions introduced; test coverage stands at 89.58% (well above the 85% requirement); 227 offline backend tests and 14 frontend tests pass without failure; frontend bundle is rebuilt, verified, and protected against drift in CI.
- **Recommended Next Step:** Approve Phase 2 sign-off and create branch `fix/phase-3-performance-reliability` from `fix/phase-2-decision-integrity` to begin Task P3.1.
