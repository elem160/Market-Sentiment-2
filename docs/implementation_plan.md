# SentimentPulse — Implementation Plan (Review Remediation)

> **Status:** APPROVED 2026-10-19 — decisions D1–D8 approved with the proposed defaults; no overrides. Progress is tracked in `docs/implementation_log.md`.
> **Baseline:** `main` @ `cab8b54` (2026-10-19) — 83/83 default tests pass, 86% coverage; `pytest -m slow` fails.
> **Scope:** every finding from the 2026-10-19 review: Critical C1–C4, High H1–H17, Medium M1–M18, Low L1–L10 (49 findings, summarised in Appendix A).
> **Location note:** this file lives in `docs/` because Windows file names are case-insensitive — `implementation_plan.md` at the root would overwrite the existing `IMPLEMENTATION_PLAN.md` (F-01…F-19). That file stays untouched until task P4.3 archives it.

## Contents

0. Prerequisites
1. Decisions requiring your approval
2. Working rules
3. Phase overview
4. Phase 0 — Safety net
5. Phase 1 — Restore the user-facing flow
6. Phase 2 — Decision integrity
7. Phase 3 — Performance, reliability, security
8. Phase 4 — Code quality & documentation
9. Database migrations
10. API and contract changes (breaking)
11. Configuration changes
12. Test strategy and verification commands
13. Manual smoke-test checklist
14. Traceability matrix
15. Risks and mitigations
16. Out of scope
- Appendix A — Findings reference

---

## 0. Prerequisites

| Item | Why | Status |
|---|---|---|
| Node.js 20 LTS (with npm) on `PATH` | Frontend type-check, build, lint, Vitest, OpenAPI type generation, rebuilding `app/static` | **Not installed on this machine** — needed before the Phase 1 frontend tasks. Backend work can start without it. |
| Python 3.11+ | Backend | Present (3.11.9) |
| Backup of `data/sentiment.db` | P0.2 cleanup and migrations 003–005 modify it | First step of P0.2 |
| Network access | Only for opt-in `live` tests and manual smoke tests | — |

---

## 1. Decisions requiring your approval

Each decision has a proposed default. Approving the plan approves the defaults unless you say otherwise.

| ID | Question | Proposed default | If you choose otherwise |
|---|---|---|---|
| D1 | Where should the news window start on weekdays? | One rule for every session: start at the **previous trading day's close** (16:00 ET, or 13:00 on early-close days), capped at 72 h. Captures after-hours earnings and, on Monday mornings, weekend news. | Keep midnight ET; P2.4 shrinks to calendar fixes plus documenting the limitation. |
| D2 | Deployment target? | **Local, single user, single worker.** API-key support is built but off by default; history stays public. | Public: `API_KEY` required, `PUBLIC_HISTORY=false`, stricter rate limits. |
| D3 | Run database migrations at startup? | Keep, behind `RUN_MIGRATIONS_ON_STARTUP=true`; document "single worker only". | Explicit `alembic upgrade head` step; flag defaults to `false`. |
| D4 | Commit the built frontend (`app/static`)? | Keep committing (README promises Node is optional); CI checks the bundle matches a fresh build. | Stop committing; build in CI/Docker; README requires Node. |
| D5 | LLM models? | Primary `nvidia/nemotron-3-ultra-550b-a55b:free`, fallback `nvidia/nemotron-3-super-120b-a12b:free`, both from config (no hardcoded IDs); `LLM_DAILY_BUDGET_USD=1.00`. | A paid fallback (e.g. `openai/gpt-4o-mini`); budget guards then matter. |
| D6 | Confidence ceilings? | Keep 0.60 (FinBERT-only) / 0.95 (hybrid), but apply the hybrid ceiling **only** when the LLM succeeded and confirmed ≥1 catalyst in the verdict's direction. No confidence floor for evidence-free HOLDs. | One ceiling for both modes (e.g. 0.85). |
| D7 | Polluted local database? | Back up, delete the fixture-based runs (10 found) and their jobs, `VACUUM`. | Delete `data/sentiment.db` entirely (loses history). |
| D8 | CI platform? | GitHub Actions (an `origin` remote exists). | Another CI with the same steps. |

---

## 2. Working rules

- One branch and one PR per phase (`fix/phase-0-safety-net`, …); small commits per task with conventional messages citing finding IDs, e.g. `fix(relevance): match forex pair notation (C3)`.
- Every phase ends green: `pytest`, `ruff check`, coverage ≥ 85%; once Node is available, `npm run typecheck && npm run build` (plus `lint`/`test` from Phase 4).
- Bugs get a failing regression test first, then the fix.
- Behaviour changes update the README in the same phase.
- Schema changes go through Alembic with a tested downgrade; `data/sentiment.db` is backed up before upgrading.
- No new runtime dependency beyond those listed here. New dev dependencies: `time-machine`, `ruff`; frontend dev: `openapi-typescript`, `vitest`, `@testing-library/react`, ESLint packages, `@fontsource/*`.

---

## 3. Phase overview

| Phase | Goal | Main findings | Migration | Depends on | Size |
|---|---|---|---|---|---|
| 0 | Safety net: isolated tests, logging, pinned deps, CI | H1, H2, H17, M17 (deps), L7 (ini), L9 (CI) | — | — | S |
| 1 | Restore the user-facing flow and truthful display | C1, C2, H10, H13, M1–M6, M9, M14, L2 | 003 | 0 | M |
| 2 | Decision integrity: relevance, corroboration, tickers, window, LLM | C3, C4, H3–H7, H14, M11, M12, L5 | 004 | 1 | L |
| 3 | Performance, reliability, security | H8, H9, H11, H12, H15, H16, M7, M8, M13, L6, L10 | 005 | 2 | L |
| 4 | Code quality and documentation | M16, M18, L1, L4, L8, L9 | — | 3 | M |

Exact finding-to-task mapping: §14.

---

## 4. Phase 0 — Safety net

### P0.1 Isolated, deterministic, offline test suite — H1, H17

**Files:** `tests/conftest.py`, `tests/fakes.py` (new), `pytest.ini`, `tests/unit/test_aggregator.py`, `tests/unit/test_freshness.py`, `tests/unit/test_ticker_service.py`, `tests/unit/test_reliability.py`, `tests/unit/test_session_window.py`, `tests/unit/test_llm_service.py`, `tests/integration/test_finbert_model_inference.py`, `tests/integration/test_live_providers.py`, `tests/fixtures/yf_current_schema.json`, `tests/fixtures/yf_legacy_schema.json` (new), `app/core/models.py`

**Changes**
1. At the top of `tests/conftest.py`, before any `app` import, point the session at throwaway state (environment variables take precedence over `.env`):
   ```python
   import os, tempfile
   _TMP = tempfile.mkdtemp(prefix="sentimentpulse-tests-")
   os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(_TMP, "test.db").replace("\\", "/")
   os.environ["OPENROUTER_API_KEY"] = ""   # never call OpenRouter from tests
   os.environ["ENABLE_LLM"] = "false"      # LLM unit tests enable it explicitly via a fixture
   os.environ["APP_ENV"] = "test"
   ```
2. A session-scoped fixture runs `app.main.run_migrations()` once against the temp DB (also exercises the migrations). A function-scoped autouse fixture deletes all rows after each test (child tables first). `db_session` uses the app's own `SessionLocal`, so request handlers, background jobs and tests share one database; the `get_db` override is removed.
3. An autouse fixture resets process-wide state between tests: `rate_limiter.reset()`, `TickerService.clear_cache()`, and drains `_background_tasks` (await with a 5 s timeout, then cancel) so no job outlives its test.
4. Network guard (autouse; skipped for tests marked `live`):
   - monkeypatch `socket.socket.connect` / `connect_ex` to reject non-loopback addresses (loopback stays allowed for the Windows asyncio self-pipe);
   - replace `yfinance.Ticker` with a stub that raises — yfinance uses curl_cffi, which bypasses Python sockets. Tests that need Yahoo data patch it explicitly, overriding the stub.
5. Determinism: add `time-machine`. A `frozen_now` fixture freezes time at Wed 2026-10-14 15:00 UTC (11:00 ET); fixture articles and aggregator helpers derive timestamps from it. A parametrised pipeline test runs at 00:30 ET, 08:00 ET and Saturday noon to prove time-independence.
6. Fix the broken or weak tests:
   - `test_finbert_model_inference.py`: pass the missing `cluster_map` (`{}`); the autouse FinBERT-mock fixture skips tests marked `slow`, so the real model loads.
   - `test_live_providers.py`: parametrise AAPL / BTC-USD / EUR/USD; assert ≥1 provider SUCCESS, non-empty titles, and that every article kept by `filter_by_session_window` is inside the window.
   - `test_multi_asset_resolution` and `test_all_rss_providers_fail…`: mock ticker resolution (no hidden Yahoo calls).
   - Replace the vacuous 72 h test with a real cap scenario (Tuesday after a Monday holiday).
   - `create_test_scored_article`: drop the invalid kwargs (`summary`, `retrieved_at_utc`, `is_cluster_rep`, `sentiment_score`, `finbert_logits`, `is_catalyst`); set `is_llm_catalyst` instead.
7. Fixtures: rewrite `yf_current_schema.json` in Yahoo's real nested format (`content.title`, `content.pubDate`, `content.provider.displayName`, `content.canonicalUrl.url`, `content.clickThroughUrl: null`); move the flat items to `yf_legacy_schema.json`.
8. `IngestedArticle` and `ScoredArticle` get `model_config = ConfigDict(extra="forbid")`, so invalid fields fail loudly.
9. `tests/fakes.py`: `KeywordScorer` (today's mock word lists) and `FakeLLMClient`; used by fixtures now and injected via DI in Phase 3.

**Acceptance**
- `pytest` passes with networking disabled, at any frozen time, and leaves `data/sentiment.db` untouched (row count and mtime unchanged).
- A guard test asserts `settings.DATABASE_URL` points into the temp directory and `settings.OPENROUTER_API_KEY == ""`.
- `pytest -m slow` passes with the cached FinBERT model; `pytest -m live` passes online.

### P0.2 Clean the polluted local database — H1 (D7)

One-off maintenance, not committed (`data/` is git-ignored):
1. Checkpoint the WAL, then copy `data/sentiment.db` to `data/sentiment.db.bak-20261019`.
2. With `PRAGMA foreign_keys=ON`, delete runs whose evidence references fixture articles (`canonical_url LIKE '%example.com%'`, IDs containing `aapl_art_`, `nvda_art_`, `_yf_1`, …) and the jobs pointing at them; then `VACUUM`.
3. Re-run the inspection query: zero fixture-based runs remain.

### P0.3 Keep application logs alive after migrations — H2

**Files:** `alembic/env.py`, `app/main.py`, `app/utils/logging.py`, `app/api/routes.py`
- `env.py`: configure logging only when invoked from the CLI, and never disable existing loggers:
  ```python
  if config.config_file_name is not None and config.attributes.get("configure_logger", True):
      fileConfig(config.config_file_name, disable_existing_loggers=False)
  ```
- `run_migrations()`: `alembic_cfg.attributes["configure_logger"] = False`.
- `logging.py`: level from a new `LOG_LEVEL` setting (default `INFO`).
- `run_background_job`: `logger.exception(...)` for unexpected errors (full traceback).

**Acceptance:** a test creates the `uvicorn.error` and `market_sentiment` loggers, runs `run_migrations()`, and asserts neither is disabled. Manual: server start shows "Database schema successfully upgraded to head", "Application startup complete", and access-log lines.

### P0.4 Dependencies, tooling and CI — M17 (deps), L7 (ini), L9 (CI)

**Files:** `requirements.txt`, `requirements-dev.txt` (new), `pyproject.toml` (new, tool config only), `alembic.ini`, `.github/workflows/ci.yml` (new), `frontend/package.json`
- `requirements.txt`: runtime dependencies pinned with `==` to the versions verified in this environment (captured with `pip freeze`; e.g. fastapi 0.147.0, pydantic 2.14.1, SQLAlchemy 2.1.5, alembic 1.20.0, httpx 0.28.1, yfinance 1.7.0, feedparser 6.0.14, openai 3.35.1, transformers 5.20.1, torch 2.14.1 CPU). Remove `beautifulsoup4` and the pytest packages; keep `tenacity` (used in P3.1) and `python-dotenv` (needed by pydantic-settings for `.env`). Document the CPU-only torch index URL.
- `requirements-dev.txt`: `-r requirements.txt` plus pytest, pytest-asyncio, pytest-cov, time-machine, ruff.
- `pyproject.toml`: ruff (`select = ["E", "F", "I", "B", "UP", "ASYNC"]`, line length 120; rules needing large rewrites ignored for now and tightened in P4.2).
- `alembic.ini`: add `path_separator = os` (removes the deprecation warning).
- `frontend/package.json`: add `"typecheck": "tsc --noEmit"`.
- CI workflow:
  - **backend** (Python 3.11 and 3.12): install deps (CPU torch), `ruff check .`, `pytest --cov=app --cov-fail-under=85`, then `alembic upgrade head` and `alembic check` on a temp DB;
  - **frontend** (Node 20): `npm ci`, `npm run typecheck`, `npm run build` (lint, tests and bundle check added later).

**Acceptance:** CI green on the phase branch.

---

## 5. Phase 1 — Restore the user-facing flow

### P1.1 One backend↔frontend contract — C1

**Backend** (`app/api/schemas.py`, `app/api/routes.py`, `app/main.py`, `scripts/export_openapi.py` new)
- Typed SSE payload models:
  ```python
  class JobProgressEvent(BaseModel):
      job_id: str; ticker: str; status: JobStatus; stage: PipelineStage
      progress_pct: float = Field(ge=0.0, le=1.0); message: str

  class JobCompletedEvent(BaseModel):
      job_id: str; status: Literal["COMPLETED"]; run_id: str; message: str

  class JobFailedEvent(BaseModel):
      job_id: str; status: Literal["FAILED"]; error_code: str; error_message: str
  ```
- Event names fixed to `progress`, `completed`, `failed` (constants in `schemas.py`); payloads serialised with `model_dump_json()`. `stage_update` is removed.
- `JobStatusResponse.status: JobStatus` and `.stage: PipelineStage` (enums appear in OpenAPI).
- Unknown job on `/jobs/{id}/events` → 404 before streaming (today: 200 plus a `failed` event).
- A custom `app.openapi()` registers the three SSE event schemas under `components.schemas` so the frontend types are generated too.
- `scripts/export_openapi.py` writes `frontend/src/api/openapi.json` (sorted keys).

**Frontend** (`src/api/schema.d.ts` generated, `src/types.ts`, `src/api/events.ts` new, `src/components/LoadingStepper.tsx`, `src/App.tsx`)
- `openapi-typescript` dev dependency; `npm run gen:api` generates `schema.d.ts`. `types.ts` re-exports aliases from it; hand-written duplicates are deleted (fixes the stale `ObservedFact` fields and the `getHealth` type).
- `SSE_EVENTS` constant mirrors the backend names.
- Stepper keys are the backend enum values: `RESOLVING_TICKER`, `INGESTING_NEWS`, `FILTERING_DEDUPLICATING`, `FINBERT_SCORING`, `CATALYST_SYNTHESIS`, `AGGREGATING_DECISION` (`DONE` = all complete).
- Progress kept as 0–1 in state, rendered as `Math.round(p * 100)%`.

**Tests**
- `tests/contract/test_openapi_snapshot.py`: `app.openapi()` equals the committed snapshot (drift fails CI; regenerate with the script).
- `tests/contract/test_sse_contract.py`: drives a job with a fake pipeline; asserts the sequence `progress…completed` and validates every payload; a failing pipeline emits `failed` with `error_message`; an unknown job returns 404.
- The CI frontend job runs `gen:api` and fails on `git diff`.

### P1.2 Robust frontend job client — C1, M6

**Files:** `frontend/src/services/api.ts`, `frontend/src/App.tsx`, `app/api/schemas.py`
- `subscribeToJob(jobId, handlers, { deadlineMs })` returns `cancel()`:
  - listens to `progress`, `completed`, `failed`; every callback checks a `cancelled` flag;
  - `completed` → close the stream → `getAnalysisResult(run_id)` → `onComplete`;
  - `failed` → close the stream → `onError(error_message)`;
  - transport `error` → if the stream is closed (or after 3 consecutive errors) → switch to polling.
- Polling uses a `setTimeout` chain (no overlapping requests), backs off 1 s → 5 s, stops on a terminal status or the deadline, honours `Retry-After` on 429, and reads `error_message` (not `error`).
- `JobCreatedResponse` gains `max_wait_seconds` (Phase 1: `PIPELINE_TIMEOUT_SECONDS + 60`; Phase 3: queue + pipeline timeouts); the client uses it as its deadline (today: a fixed 40 s).
- `App.tsx` keeps an `activeJobRef`; a new search or a history selection cancels the previous subscription; late callbacks from old jobs are ignored.
- `parseApiError()` understands the unified error shape (P1.7) and FastAPI's legacy `detail`.

**Tests (Vitest with fake `EventSource` and `fetch`):** progress mapping; `failed` shows the backend text; polling fallback after a transport error; cancellation prevents a late `onComplete`; deadline taken from the server.

### P1.3 Always persist results; caching becomes a flag — C2 (migration 003)

**Files:** `alembic/versions/003_persistence_integrity.py`, `app/db/models.py`, `app/db/repository.py`, `app/services/orchestrator.py`, `tests/unit/test_reliability.py`, `tests/e2e/test_job_flow.py` (new)
- New column `analysis_runs.is_cacheable BOOLEAN NOT NULL DEFAULT 1`.
- `save_analysis_run(..., is_cacheable: bool)`; `get_cached_run()` filters on `is_cacheable`.
- Orchestrator: both "skip saving when all RSS feeds failed" branches are removed; runs are always saved with `is_cacheable = not all_rss_failed` (becomes `DataStatus.DEGRADED` in P2.6).
- `test_all_rss_providers_fail…` now asserts the run **is** retrievable by ID but never returned from the cache.
- New e2e test: job completes → `GET /analysis/{run_id}` → 200, including the all-RSS-failed path.

### P1.4 Stable article IDs, truthful cache status — H13, L3 (columns), L4 (fact IDs), M14 (length)

**Files:** migration 003 (continued), `app/db/models.py`, `app/db/repository.py`
- New column `article_evidence.article_id VARCHAR(64)`: added nullable → backfilled with `UPDATE article_evidence SET article_id = substr(id, length(run_id) + 2)` → set NOT NULL (batch mode) → unique index on `(run_id, article_id)`. The `id` primary key stays (opaque).
- `_to_analysis_result()` returns `a.article_id`, so fresh and reloaded results match and `ObservedFact.cited_article_id` links resolve.
- `cache_status`: `get_analysis_run()` returns the stored value (`MISS` for computed runs); only the cache path of `/analyze` reports `HIT`.
- `ObservedFactDB.id` becomes a `uuid4()` (no prefix collisions).
- `ticker` columns widened to `VARCHAR(32)` (jobs, runs); the model's `data_status` length aligned with migration 002 (30).
- Downgrade drops the column and index and restores the lengths.

**Tests:** save → reload → identical article IDs and facts resolve to articles; `/analysis/{id}` of a fresh run → `MISS`; a second `/analyze` → `HIT`; migration round trip with seeded rows.

### P1.5 Timezone-aware timestamps end to end — M2, M14

**Files:** `app/db/types.py` (new), `app/db/models.py`, `app/db/repository.py`, `app/api/schemas.py`
- `UTCDateTime(TypeDecorator)`: on write, converts aware datetimes to UTC (naive values rejected); on read, attaches `timezone.utc`. Storage format unchanged → no migration, and `alembic check` stays clean.
- Every `Column(DateTime …)` uses it; the manual `.replace(tzinfo=…)` patches in the repository are deleted.
- `RecentRunSummary.run_timestamp_utc: datetime` (serialised with `Z`); adds `asset_type` and `data_status` for the History list.

**Tests:** round trip keeps UTC; `/history` timestamps end in `Z` or `+00:00`.

### P1.6 Truthful UI — M1, M2, M3, M4, M5, M10 (part)

**Backend** (no migration — metrics are stored as JSON)
- `PipelineMetrics` gains `excluded_counts: dict[ExclusionReason, int]` (true totals per reason), `articles_excluded_total` and `directional_threshold`.
- `articles_deduplicated` counts only `DUPLICATE_SYNDICATION` exclusions.

**Frontend**
- `src/utils/time.ts`: `formatInTimeZone(iso, tz)` and `formatUtc(iso)`; ET via `Intl.DateTimeFormat(..., { timeZone: 'America/New_York' })`.
- `SessionWindowBanner` (M1): the ET row shows real ET; prop renamed `window` → `session`.
- `DecisionHero` (M3):
  - "Cached result" badge only when `cache_status === 'HIT'` (no hardcoded "15m");
  - retained count from `metrics.articles_retained`;
  - confidence labels High / Moderate / Low (no "Multi-Source Corroborated");
  - the corroboration badge switches to `metrics.supporting_publishers` in P2.1.
- `EvidenceExplorer` (M4):
  - filters by `finbert_directional_score` against `metrics.directional_threshold`, so tab counts equal the rationale's tallies;
  - the excluded section is grouped by reason and shows "N of M" from `excluded_counts`;
  - shows "age at run: Xh"; no link when the URL is empty.
- `RationaleSection` (M5): a new **LLM Catalyst Synthesis** card (`llm_summary`, model from `model_versions.llm`); facts joined to articles via `cited_article_id` → publisher, time, category and impact badges.
- `TelemetryDrawer`: "Excluded: total (breakdown)" instead of "Dups"; feed health once P3.1 exposes `provider_outcomes`.
- `HistorySidebar` (M2): date and time with a timezone label.
- `App.tsx`: multi-asset empty-state copy; no hardcoded "15-minute cache" text.

**Tests (Vitest):** ET formatting including DST boundaries; filter counts equal the backend tallies for a fixture result; the LLM card renders; facts show publisher and time.

### P1.7 Unified errors and an honest health check — M9

**Files:** `app/main.py`, `app/api/routes.py`, `app/core/exceptions.py`
- Exception handlers, all returning `{error, message, details}`:
  - `SentimentAppException` (adds `Retry-After` for `RateLimitExceededException`);
  - `RequestValidationError` → 422 with field errors in `details`;
  - Starlette `HTTPException` → same shape;
  - any other `Exception` → 500 with `details.error_id`; full traceback logged.
- Routes raise domain exceptions (`JobNotFoundException`, `AnalysisRunNotFoundException`, rate-limit and ticker errors) instead of `HTTPException`.
- Background job failures: domain errors keep their user-safe message; unexpected errors become `"Internal error (ref <error_id>)"`.
- `/health`: `status` `UP` or `DEGRADED`; HTTP 503 when the DB check fails; no raw exception text; `finbert_status` from the service's real state (`NOT_LOADED`, `LOADING`, `LOADED`, `FAILED`) — fixes the class-vs-instance attribute bug.

**Tests:** shape and status for 404 / 422 / 429 / 500; `Retry-After` present; health 503 with a broken DB; health reports `LOADED` after loading.

### P1.8 Hotfixes — H10, L2

- `parse_yfinance_items()`: null-safe access through `_as_dict(value) -> dict` for `content`, `canonicalUrl`, `clickThroughUrl` and `provider`; `publisher = str(... or "").strip()`.
- `AggregatorService`: raise `FreshnessViolationException(article_id=..., timestamp_str=..., window_start=..., window_end=...)` with keyword arguments.

**Tests:** the current-schema fixture with `clickThroughUrl: null` parses; the exception message names the article.

### P1.9 Rebuild and commit the bundle (D4)

`npm run gen:api && npm run build`; commit `app/static`; CI verifies the committed bundle equals a fresh build.

**Phase 1 done when:** the e2e test (submit → SSE progress → completed → result) passes, including the all-RSS-failed path, and smoke checks 1–3 and 8 (§13) pass.

---

## 6. Phase 2 — Decision integrity

### P2.1 Corroboration by direction — C4, M11, M3 (badge)

**Files:** `app/core/models.py`, `app/services/news_service.py`, `app/services/finbert_service.py`, `app/services/aggregator_service.py`, `alembic/versions/004_decision_integrity.py`
- `ScoredArticle.publisher_inferred: bool = False`, copied from `raw_provider_metadata` during scoring and persisted (`article_evidence.publisher_inferred BOOLEAN NOT NULL DEFAULT 0`).
- `parse_rss_feed_content(..., publisher_is_authoritative: bool)`: direct publisher feeds (Investing.com, FXStreet) are authoritative; only Google sweeps lacking `<source>` set `publisher_inferred=True`.
- The aggregator keeps separate sets of eligible publishers, `pos_publishers` and `neg_publishers` (excluding "Unknown Aggregator" and inferred ones). BUY requires `len(pos_publishers) ≥ 2`, SELL requires `len(neg_publishers) ≥ 2`; otherwise HOLD with `INSUFFICIENT_CORROBORATION`.
- Evidence quality's diversity factor uses the supporting side's count (for BUY/SELL candidates) or the larger side (otherwise); zero publishers gives factor 0.5 (today treated as one publisher).
- The redundant `n_valid < 2` check is removed; rationale lines name both sides' publisher counts.
- Metrics: `publishers_positive`, `publishers_negative`, `supporting_publishers` (used by the UI badge).
- README decision matrix: `P_distinct` → `P_support`.

**Tests:** 2 positive Reuters + 1 negative CNBC → HOLD + `INSUFFICIENT_CORROBORATION` (today: BUY); positive Reuters + CNBC vs 1 negative → BUY; only inferred publishers → HOLD; aggregator publishers ignored.

### P2.2 Relevance engine rebuild — C3, H4, M15 (queries)

**Files:** `app/services/relevance.py` (new), `app/core/asset_registry.py` (new), `app/services/deduplication_service.py`, `app/services/news_service.py`, `tests/unit/test_relevance.py` (new), `tests/fixtures/relevance_cases.json` (new)
- `RelevanceMatcher.for_asset(asset)` compiles every pattern once per run and exposes `match(title, summary) -> reason | None` (reasons: `CASHTAG`, `EXCHANGE_TICKER`, `TICKER`, `ALIAS`, `NAME`, `PAIR`, `CURRENCY_NAMES`, `KEYWORD`). `process_and_deduplicate()` takes the matcher; `is_materially_relevant()` is removed.
- `asset_registry.py` contains:
  - `EQUITY_ALIASES` for ~50 large caps and popular ETFs (e.g. GOOGL/GOOG → Google, Alphabet; META → Meta Platforms, Facebook; BRK-B → Berkshire Hathaway; AMD → Advanced Micro Devices; T → AT&T; SPY → S&P 500 ETF), each flagged `ambiguous` when it is also a common word (Target, Gap, Visa, Ford, Shell…);
  - `COMMON_WORD_TICKERS` (NOW, ALL, ARE, HAS, CAT, KEY, LOW, ON, IT, AI, BIG, FUN, CAR, EAT, GOOD, WELL, FAST, MAIN, PLAY, OPEN, REAL, SAFE, TRUE, BEST, LIFE, WORK, ONE…);
  - `CURRENCY_NAMES` (EUR → euro; USD → dollar, greenback; JPY → yen; GBP → sterling, pound, cable; CHF → franc, swissie; AUD → Australian dollar, Aussie; CAD → Canadian dollar, loonie; NZD → New Zealand dollar, kiwi; CNY → yuan, renminbi…);
  - `FUTURES_KEYWORDS` (GC=F gold, bullion; SI=F silver; CL=F crude, oil, WTI, OPEC; BZ=F Brent; NG=F natural gas, Henry Hub; HG=F copper; ZW=F wheat; ZC=F corn; ZS=F soybean(s); ES=F S&P 500, SPX, E-mini; NQ=F Nasdaq 100, NDX; YM=F Dow; RTY=F Russell 2000);
  - `CRYPTO_NAMES` (BTC Bitcoin; ETH Ethereum, Ether; SOL Solana; XRP Ripple; DOGE Dogecoin; …).
- **Equity rules**, in order:
  1. cashtag;
  2. exchange-prefixed ticker (`NASDAQ: AAPL`, `NYSE:T`);
  3. bare ticker, **case-sensitive** on the original text, length ≥ 2, not in `COMMON_WORD_TICKERS` (`BRK-B` also matches `BRK.B`);
  4. non-ambiguous aliases (case-insensitive);
  5. ambiguous aliases only with a market-context term elsewhere in the text (shares, stock, earnings, revenue, sales, guidance, CEO, retailer, Inc, Corp…);
  6. full cleaned company name;
  7. first distinctive name token, only in Title Case and only if not generic (generic list extended with micro, general, advanced, united, american, national, global, digital, energy, capital, financial, motors…).
- **Forex rules:**
  - the pair in either order and any notation (`EUR/USD`, `EURUSD`, `EUR-USD`, `EUR USD`);
  - or both currency names — USD's "dollar" doesn't count after Australian / Canadian / New Zealand / Hong Kong / Singapore / Aussie;
  - for USD-quoted majors, the non-USD leg's name alone ("yen", "euro", "sterling");
  - never relevant when the text names a different explicit pair but not ours (e.g. "EUR/JPY" for EUR/USD).
- **Futures/commodity rules:** keyword list, case-insensitive, with exclusions (palm / olive / cooking oil).
- **Crypto rules:** cashtag, case-sensitive symbol, names, `BTC-USD` / `BTC/USD`.
- **Google queries (M15)** are built from the registry: equities `("Apple" OR AAPL)`, forex `("EUR/USD" OR EURUSD)`, futures `("crude oil" OR WTI)`, crypto `(Bitcoin OR BTC)`; site sweeps reuse the same subject.

**Tests:** table-driven `relevance_cases.json` (~60 cases):
- every probe case from the review: EUR/USD and USD/JPY headlines, "Dollar slips against the euro", EUR/JPY vs EUR/USD, NOW/ALL, Google vs GOOGL, oil vs CL=F, S&P 500 vs ES=F, micro-cap vs AMD;
- all existing relevance tests: GM vs General Electric, TGT vs "inflation target", AMD vs advanced manufacturing, AT&T, short tickers;
- real headlines exported from your database — e.g. "EUR/USD Sliding as French Unrest Returns" must be relevant to EUR/USD.

### P2.3 Ticker resolution — H3, H5, M16 (TTL cache)

**Files:** `app/services/ticker_service.py`, `app/api/routes.py`, `app/services/orchestrator.py`, `app/core/models.py`, `app/core/enums.py`, `app/core/exceptions.py`
- Input is parsed once into `(normalized, bypass_aliases)`. The resolution cache is keyed by both, with a TTL (`TICKER_CACHE_TTL_SECONDS`, default 6 h) and a 10-minute negative cache for not-found symbols. The cross-mode write `_resolution_cache[display_ticker] = asset` is removed.
- Not found: if Yahoo answered (no transport error) but there is no quote type **and** no 5-day price history → `TickerNotFoundException` (404). Transport errors → resolve as unverified (`Asset.verified = False`) and add a result warning.
- Resolution runs in a thread with `TICKER_RESOLUTION_TIMEOUT_SECONDS`; a timeout → 503 `ProviderException("Yahoo Finance", ...)`.
- The resolved `Asset` is passed into the job: `run_background_job(job_id, asset, …)` → `run_pipeline(asset=asset, …)`. The orchestrator no longer re-resolves, so the `$` intent survives.
- Asset typing: ES=F, NQ=F, YM=F, RTY=F → `AssetType.FUTURES` (the dormant enum; news domains = equity publishers); exchange labels from Yahoo or the registry (crypto `CCC`, forex `CCY`).
- Messages updated for multi-asset ("could not be resolved on Yahoo Finance").

**Tests:** GOLD → GC=F, then $GOLD → GOLD (equity), then GOLD → still GC=F; $CORN; unknown symbol → 404; transport error → unverified plus warning; TTL expiry (time-machine); the orchestrator never calls `validate_and_resolve`.

### P2.4 Session window and market calendar — H14, L5, M13 (buckets) (D1)

**Files:** `app/core/session_window.py`, `app/core/market_calendar.py` (new), `tests/unit/test_session_window.py`, `README.md`
- Calendar module: NYSE holidays (Juneteenth only from 2022), **early closes** (13:00 ET) and special closures (e.g. 2025-01-09) as explicit dated tables for 2025–2027, verified against nyse.com at implementation time, with rule-based fallback for other years.
- One window rule for every session: `window_start` = close of the most recent trading day before today's ET date (16:00, or 13:00 after an early close), capped at `run − 72 h`; `window_end = run`. Session type and `is_market_open` keep their logic but respect early closes.
- Cache buckets: floor by minutes since midnight ET (supports buckets over 60 min); settings validated (1–1440 and dividing 1440).

**Tests:**
- Wed 14:30 → start Tue 16:00 (22.5 h)
- Mon 08:00 → start Fri 16:00 (64 h, weekend included)
- Tue 00:30 → start Mon 16:00 (8.5 h)
- Tue after Memorial Day → capped at 72 h
- Mon after the day-after-Thanksgiving early close → start Fri 13:00
- DST switch days
- 120-minute bucket flooring

### P2.5 LLM robustness — H6, H7, M10 (LLM metric), M17 (pricing)

**Files:** `app/services/llm_service.py`, `app/config.py`, `app/main.py` (lifespan), `tests/unit/test_llm_service.py`
- One shared `AsyncOpenAI` client (`timeout=httpx.Timeout(LLM_REQUEST_TIMEOUT_SECONDS, connect=5)`, `max_retries=LLM_MAX_RETRIES` = 1), created lazily and closed at shutdown.
- Models tried: `[LLM_MODEL_ID]` plus `LLM_FALLBACK_MODEL_ID` if set — no hardcoded IDs (defaults per D5).
- Overall deadline `asyncio.wait_for(attempts, LLM_TIMEOUT_SECONDS)` (30 s); a timeout → `FAILED` → FinBERT-only result instead of a failed job.
- Request: `temperature=0`; `response_format={"type": "json_object"}` when `LLM_JSON_MODE` (retried once without it if the provider rejects it); `extra_body={"reasoning": {"effort": LLM_REASONING_EFFORT, "exclude": True}}` when set, so reasoning models don't spend the token budget.
- An attempt fails, moving to the next model, on: `finish_reason == "length"`, empty content, or JSON that doesn't validate against `LLMCatalystResponse` (`catalysts: list[{index, category}]`, `catalyst_indices: list[int]`, `synthesis_summary: str`). All attempts failed → `FAILED`. Valid JSON with zero catalysts stays `SUCCESS`.
- Prompt hardening: escape `&` first, then `<` and `>`; strip control characters; titles ≤ 200 chars, publishers ≤ 60; drop the lowest-confidence candidates until the estimate fits `MAX_PROMPT_TOKENS` (the setting finally does something).
- Budget checked per model before each attempt (plus the daily budget from P3.6).
- Telemetry records `attempts: [{model, outcome, latency_ms}]` and the real `candidates_sent`, which feeds `metrics.articles_sent_to_llm` (0 when skipped).
- Pricing table refreshed (deepseek-chat 0.32 / 0.89 USD per M tokens, Nemotron Ultra paid 0.60 / 2.40, Super paid 0.08 / 0.45, `:free` variants 0), overridable via a `MODEL_PRICING` JSON env value; prices re-verified at implementation time.

**Tests:** a slow fake client → `FAILED` within the deadline while the pipeline still completes; `max_retries` passed through; no hardcoded fallback; `finish_reason="length"` → next model; invalid JSON → `FAILED` plus deterministic mode; prompt sanitisation; `MAX_PROMPT_TOKENS` trimming; per-model budget skip; client closed on shutdown.

### P2.6 Data status, HOLD reasons, confidence — M12 (D6)

**Files:** `app/core/enums.py`, `app/core/models.py`, `app/services/orchestrator.py`, `app/services/aggregator_service.py`, `app/db/repository.py`, migration 004, frontend
- `DataStatus` enum: `OK`, `NO_FRESH_NEWS`, `NO_RELEVANT_NEWS`, `DEGRADED`.
  - Nothing survives relevance/dedup → `NO_RELEVANT_NEWS` (HOLD, confidence 0, FinBERT and LLM skipped).
  - All RSS feeds failed → `DEGRADED` (saved, not cacheable).
- Cache TTL for `NO_FRESH_NEWS` and `NO_RELEVANT_NEWS`: min(bucket, 300 s).
- `HoldReason` enum (`NO_NEWS`, `SPARSE_EVIDENCE`, `INSUFFICIENT_CORROBORATION`, `CONFLICTING`, `NEUTRAL`), stored in `analysis_runs.hold_reason` (migration 004).
- Confidence: 0.0 for `NO_NEWS` / `SPARSE_EVIDENCE` (no floor); the 0.95 hybrid ceiling applies only when the LLM succeeded and confirmed ≥1 catalyst supporting the verdict's direction, otherwise 0.60.
- The UI shows the HOLD reason and "n/a" confidence for evidence-free HOLDs.

**Tests:** irrelevant-only news → `NO_RELEVANT_NEWS` with the short TTL; a degraded run is not cacheable; ceilings per D6; HOLD reasons per rule.

### P2.7 Documentation for Phase 2 behaviour

README sections on the session window, relevance rules, corroboration, data statuses, HOLD reasons and confidence updated in the same PR.

**Phase 2 done when:** the relevance, corroboration, ticker and session-window suites pass; an LLM timeout or garbage reply degrades to FinBERT-only; smoke checks 4–6 pass.

---

## 7. Phase 3 — Performance, reliability, security

### P3.1 Ingestion rework — H9, M15 (dedup order), M10 (total_sources), L10 (part)

**Files:** `app/services/news_service.py`, `app/services/deduplication_service.py`, `app/main.py`, `app/core/models.py`, `app/services/orchestrator.py`
- One shared `httpx.AsyncClient` created in the lifespan (User-Agent from `HTTP_USER_AGENT`, `Timeout(8, connect=4)`, connection limits, redirects) and closed at shutdown. It's handed to the pipeline through a `PipelineDeps` container, which also carries the scorer, the LLM service and the session factory.
- A `FeedSpec` list and a `ProviderOutcome` model (`key`, `kind` = `YFINANCE` / `RSS_GOOGLE` / `RSS_DIRECT`, `status`, `count`, `latency_ms`, `error_code`); the orchestrator's outage logic uses `kind`, not key prefixes.
- Yahoo (`get_news(count=YF_NEWS_COUNT)`, default 50, on an I/O executor) and **all** feeds start together; `asyncio.wait(tasks, timeout=INGESTION_TIMEOUT_SECONDS)` keeps partial results and marks stragglers `TIMEOUT`.
- Feeds retry once with jitter (tenacity) on 429 / 5xx / timeouts. Responses that aren't feeds (HTML content type, or no feed version and no entries — e.g. consent pages) → `FAILED("NOT_A_FEED")`.
- Ingestion only drops exact duplicates (same `article_id`); title and near-duplicate handling moves after the freshness filter and prefers dated, earliest copies.
- `metrics.total_sources` = providers attempted (no synthetic key). `AnalysisResult.provider_outcomes` is exposed (read from `provider_outcomes_json`) for a feed-health view in Telemetry.
- `canonicalize_url()` no longer mutates its input; non-http(s) URLs become empty (L10). Jaccard token sets are computed once per article.

**Tests:** all fetchers start before any finishes; the global timeout keeps partial results; HTML 200 → `FAILED`; 503-then-200 retry succeeds; the Yahoo count is passed; outcome kinds drive outage detection.

### P3.2 FinBERT throughput and dependency injection — H8, M16 (mock)

**Files:** `app/services/finbert_service.py`, `app/services/scoring.py` (new), `app/main.py`, `app/services/orchestrator.py`, `tests/fakes.py`, `scripts/bench_finbert.py` (new)
- A `SentimentScorer` protocol (`load()`, `state`, `async score(texts) -> list[ClassProbs]`); `FinBERTScorer` imports transformers/torch lazily inside `load()`.
- Inference runs on a dedicated single-thread executor (serialised across jobs) as one batched call per chunk: `pipeline(texts, batch_size=FINBERT_BATCH_SIZE, truncation=True, max_length=512)`. No encode/decode round trip; output normalised across transformers versions; optional `torch.set_num_threads(FINBERT_TORCH_THREADS)`; cancellation checked between chunks.
- Preload in the lifespan when `FINBERT_PRELOAD=true` (non-blocking); jobs wait for readiness within their timeout; `/health` reports the state.
- `lead_text` is built at the source (title + summary, ≤ 500 chars), so the orchestrator's O(n²) patch is deleted.
- Mock code (`set_mock_mode`, `_is_mock`, `_mock_fn`) and `MAX_EXCERPT_TOKENS` are removed; tests inject `KeywordScorer` via `PipelineDeps`.

**Tests / acceptance:** one batched call per chunk; output normalisation; cancellation; the slow test uses the real scorer; `bench_finbert.py` shows ≥ 1.8× throughput vs the per-article loop on the same machine (measured baseline: 106 ms → 52 ms per article).

### P3.3 Stop blocking the event loop — H11

**Files:** `app/utils/executors.py` (new), `app/db/database.py`, `app/api/routes.py`, `app/services/orchestrator.py`
- Dedicated executors — `db_executor` (4 threads), `io_executor` (4 threads, yfinance), FinBERT's own (P3.2) — shut down in the lifespan.
- `await run_db(fn, *args)` runs a repository call on `db_executor` with its own session; used by the orchestrator, the progress callback and async routes. DB-only routes become plain `def` handlers.
- SQLite `PRAGMA busy_timeout=5000`.

**Tests:** while a fake slow DB write is running, `/api/v1/health` answers in < 200 ms.

### P3.4 Job manager: limits, coalescing, SSE — M7, M8, H15 (concurrency), L6

**Files:** `app/services/job_manager.py` (new), `app/api/routes.py`, `app/api/schemas.py`, `app/main.py`; `app/utils/lock_manager.py` deleted
- `JobManager` on `app.state`:
  - `submit()` computes the cache key and returns the **in-flight job** for that key (`coalesced: true`) or creates a new one;
  - a global `asyncio.Semaphore(MAX_CONCURRENT_PIPELINES)` (default 2); waiting jobs stay `QUEUED` with "Waiting for a worker (N ahead)";
  - `JOB_QUEUE_TIMEOUT_SECONDS` → `FAILED("QUEUE_TIMEOUT")`; `PIPELINE_TIMEOUT_SECONDS` covers the run itself;
  - progress is published to an in-process channel and persisted via `run_db`;
  - shutdown cancels tasks, marks their jobs `CANCELLED`, and awaits them with a timeout.
- SSE subscribes to the channel (falling back to 1 s DB polling when the job isn't in this process), sends a heartbeat comment every `SSE_HEARTBEAT_SECONDS` (15), uses a deadline of queue + pipeline timeouts + 15 s, stops when the client disconnects, and measures time with `time.monotonic()`.
- `JobCreatedResponse` gains `coalesced` and the final `max_wait_seconds`.

**Tests:** two identical submissions → same `job_id`; a limit of 1 with 3 jobs runs them sequentially; queue timeout → `FAILED`; heartbeat and event order; shutdown marks running jobs `CANCELLED`.

### P3.5 Rate limiting and client IP — H12

**Files:** `app/utils/rate_limiter.py`, `app/api/dependencies.py`, `app/api/routes.py`, `app/config.py`
- `check(scope, key, limit, window)` with separate scopes: `analyze` (15/min), `jobs` (60/min, status + events), `read` (120/min, analysis + history); the key store is bounded (LRU at 10 000 keys).
- `Depends(rate_limit("analyze", ...))` dependencies replace the inline try/except; 429 responses carry `Retry-After`.
- Client IP: if `TRUST_PROXY_HEADERS` is on and the direct peer is in `TRUSTED_PROXY_IPS` (CIDR allowed), walk `X-Forwarded-For` right to left, skipping trusted proxies; otherwise use the peer address. README documents uvicorn's `--proxy-headers --forwarded-allow-ips`.

**Tests:** 15 job polls don't block `/analyze`; a spoofed leftmost XFF value is ignored; a trusted proxy chain resolves; `Retry-After` header present; LRU cap holds.

### P3.6 Cost, abuse and input controls — H15 (cost), L3 (input), L10 (D2)

**Files:** `app/api/dependencies.py`, `app/api/schemas.py`, `app/services/ticker_service.py`, `app/services/llm_service.py`, `app/main.py`, `alembic/versions/005_operations.py`
- Optional `API_KEY`: when set, `POST /analyze` requires `X-API-Key`; with `PUBLIC_HISTORY=false`, `/history` and `/analysis/{id}` require it too.
- Daily LLM budget: new column `analysis_runs.llm_cost_usd` (backfilled from `metrics_json` on SQLite). Before an LLM call, if today's UTC spend ≥ `LLM_DAILY_BUDGET_USD` → `SKIPPED("DAILY_BUDGET_EXCEEDED")`.
- `AnalyzeRequest.ticker`: `min_length=1, max_length=20`; `normalize_ticker()` enforces a maximum length for every notation.
- CORS `allow_credentials=False` (no cookies are used); a security-headers middleware adds `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and a basic CSP.

**Tests:** missing or wrong key → 401 when a key is configured; an exhausted budget skips the LLM; a 21-character ticker → 422; headers present.

### P3.7 Data lifecycle — H16

**Files:** `app/services/deduplication_service.py`, `app/services/maintenance.py` (new), `app/cli.py` (new), `app/main.py`, migration 005
- Relevance, duplicate and capacity exclusions: all counted, but at most `MAX_EXCLUDED_SAMPLES_PER_REASON` (20) samples stored per reason; totals go to `metrics.excluded_counts`.
- Retention: an hourly lifespan task deletes jobs past `expires_at` and runs older than `RUN_RETENTION_DAYS` (30; evidence and facts cascade). `python -m app.cli maintenance [--vacuum]` runs it manually.
- Indexes on `analysis_runs.created_at` and `analysis_jobs.expires_at` (migration 005).

**Tests:** purging removes old runs with their evidence and facts and keeps recent ones; at most 20 samples per reason with correct totals.

### P3.8 Configuration and startup — M13, L7 (env.py)

**Files:** `app/config.py`, `app/db/database.py`, `alembic/env.py`, `app/main.py`, `app/__main__.py` (new), `app/services/orchestrator.py`, `.env.example`, `tests/unit/test_config.py` (new)
- `BASE_DIR` resolved from the package; `.env` read from `BASE_DIR`; relative SQLite paths resolved against `BASE_DIR` in a settings validator, so the app, migrations and tests always agree. The duplicated path logic in `database.py`, `main.py` and `env.py` (including the default-URL string hack) is removed; `env.py` uses `settings.DATABASE_URL` unless `-x db_url=…` is given.
- `RUN_MIGRATIONS_ON_STARTUP` (D3); README states single-worker deployment.
- Cache key = `sha256(ALGORITHM_VERSION, ticker, asset_type, bucket, enable_llm, config_hash)`. `config_hash` includes the fallback model and the decision thresholds; `ALGORITHM_VERSION` is bumped whenever scoring rules change (this plan sets it to `2`).
- Startup warning when `INGESTION_TIMEOUT + LLM_TIMEOUT + expected FinBERT time ≥ PIPELINE_TIMEOUT`.
- `python -m app` runs uvicorn with `APP_HOST` / `APP_PORT` (now used), `workers=1` and the proxy settings.
- `.env.example` lists every setting with a comment; the config test checks that every `Settings` field appears there with the same default.

**Tests:** starting from another working directory uses the project's DB and `.env`; the config hash changes with the fallback model; invalid bucket sizes are rejected.

**Phase 3 done when:** a 350-article run finishes well inside the timeout, a concurrent-load test shows no event-loop stalls, the DB stays bounded, and smoke checks 7, 9 and 10 pass.

---

## 8. Phase 4 — Code quality & documentation

### P4.1 Orchestrator refactor — M16

Split `run_pipeline` into stage methods over a `PipelineContext` (`_ingest`, `_filter_fresh`, `_select_relevant`, `_score`, `_synthesize`, `_aggregate`, `_build_result`, `_persist`). A `build_excluded_article()` helper replaces the two duplicated blocks; a `DISCLAIMER` constant replaces three copies; metrics are built in one function. A golden-snapshot test of a deterministic run (result minus IDs and timestamps), recorded before the refactor, guards against behaviour changes.

### P4.2 Dead code and lint — L1

- Remove: `UnsupportedAssetException`, `BudgetExceededException`, `ProviderType.FINNHUB`, `ExclusionReason.CATALYST_REJECTED_AS_NOISE`, `AssetType.INDEX`, the old `LLMSynthesisResponse`, unused imports (`HttpUrl`, …), the unused `company_name` aggregator parameter, and stale "US equities/ETFs, Version 1.0" texts. None of these values were ever stored in the database.
- Already put to use in earlier phases: `JobNotFoundException`, `AnalysisRunNotFoundException`, `ProviderException`, `AssetType.FUTURES`, `JobStatus.CANCELLED`, `APP_HOST` / `APP_PORT`, `MAX_PROMPT_TOKENS`.
- Ruff rules tightened; CI enforces them.

### P4.3 Documentation — M18

- README rewritten to match the code:
  - honest feature claims (no "durable", "token-sort", "2–3 s");
  - architecture diagram with the JobManager and executors;
  - API reference: SSE contract, job statuses including `QUEUED` and `CANCELLED`, unified errors, rate limits;
  - configuration table;
  - decision model: directional corroboration, HOLD reasons, confidence;
  - session window and relevance rules;
  - limitations: single worker, jobs cancelled on restart, Google redirect links, free-model rate limits;
  - measured performance and testing guarantees (offline suite, markers);
  - accurate project tree and the Node requirement per D4.
- Root `IMPLEMENTATION_PLAN.md` moved to `docs/history/2026-10_remediation_F01-F19.md`; `docs/CHANGELOG.md` created with v1.1.0; version bumped to 1.1.0 in `app/main.py` and `frontend/package.json`.

### P4.4 Frontend quality — L8

- ESLint (flat config: typescript-eslint, react-hooks, jsx-a11y) and `npm run lint`.
- Accessibility: clickable `div`s become `<button>`s with `aria-expanded`; visible focus styles; `prefers-reduced-motion` support.
- CSS: `.btn-link` and `.no-fresh-news-banner` defined (inline styles moved into CSS); unused keyframes removed; narrow-screen layout for the header and search bar.
- Self-hosted fonts via `@fontsource/*` (no external requests).
- `formatTickerLabel()` shows `$` only for equities/ETFs; the search input syncs with `activeTicker`; toned-down meta description.
- Vitest + Testing Library tests for the touched components; CI runs `lint` and `test`.

### P4.5 Repository hygiene — L9 (D4)

Delete the stale root `__pycache__/` (untracked); in `.gitignore`, change `lib/` to `/lib/` and add `data/*.bak*`; CI bundle check per D4; optional `Dockerfile` (python 3.12-slim, CPU torch, non-root user, `python -m app`) with `.dockerignore`.

### P4.6 Persistence details — L4

`ScoredArticle.retrieved_at_utc` carried from ingestion and stored (no longer overwritten at save time); `_to_analysis_result()` rebuilds `SessionWindow` from the stored window columns (plus derived ET values) instead of recomputing it from the calendar.

**Phase 4 done when:** strict ruff, ESLint and Vitest pass in CI; the README is checked against the running app; v1.1.0 is tagged.

---

## 9. Database migrations

| Revision | Phase | Changes | Backfill | Downgrade |
|---|---|---|---|---|
| `003_persistence_integrity` | 1 | `analysis_runs.is_cacheable` (bool, default true); `article_evidence.article_id` (varchar 64, NOT NULL after backfill) + unique `(run_id, article_id)`; `ticker` → varchar 32 (jobs, runs); `data_status` length aligned to 30 | `article_id = substr(id, length(run_id) + 2)` | Drop column and index; restore lengths |
| `004_decision_integrity` | 2 | `article_evidence.publisher_inferred` (bool, default false); `analysis_runs.hold_reason` (varchar 30, nullable) | None (old rows: false / NULL) | Drop columns |
| `005_operations` | 3 | `analysis_runs.llm_cost_usd` (float, default 0); indexes on `analysis_runs.created_at` and `analysis_jobs.expires_at` | SQLite: `json_extract(metrics_json, '$.estimated_cost_usd')` | Drop column and indexes |

`tests/integration/test_migrations.py` replaces `test_migration_002.py`: it seeds data at each revision, upgrades base → head, checks the backfills, and downgrades head → base. CI also runs `alembic check` (models vs migrations).

---

## 10. API and contract changes (breaking)

| Area | Before | After |
|---|---|---|
| SSE progress event | `event: stage_update` | `event: progress` |
| SSE failure payload | `{error}` | `{error_code, error_message}` |
| SSE for an unknown job | 200 + `failed` event | 404 |
| Error responses | Mixed `{detail}` and `{error, message, details}` | Always `{error, message, details}`; 429 adds `Retry-After` |
| `/analysis/{id}` | `cache_status` always `HIT`; article IDs `run_id_articleid` | Stored `cache_status`; original article IDs |
| `/history` | Naive timestamps | Aware timestamps (`Z`) plus `asset_type` and `data_status` |
| `POST /analyze` | Always a new job | May return the in-flight job (`coalesced: true`); `max_wait_seconds`; ticker ≤ 20 chars; optional `X-API-Key` |
| `AnalysisResult` | — | New `hold_reason`, `provider_outcomes`; `data_status` adds `NO_RELEVANT_NEWS` and `DEGRADED`; metrics add `excluded_counts`, `directional_threshold`, `publishers_positive`, `publishers_negative`, `supporting_publishers` |
| `/health` | Always 200 / `UP` | 503 when the DB is down; `finbert_status` is `NOT_LOADED`, `LOADING`, `LOADED` or `FAILED` |
| Session window | Midnight ET on weekdays | Previous trading day's close (D1) |
| Job statuses | `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED` | Adds `CANCELLED` (shutdown) |

---

## 11. Configuration changes

**New settings**

| Setting | Default | Phase |
|---|---|---|
| `LOG_LEVEL` | `INFO` | 0 |
| `TICKER_CACHE_TTL_SECONDS` | `21600` | 2 |
| `TICKER_RESOLUTION_TIMEOUT_SECONDS` | `15` | 2 |
| `LLM_TIMEOUT_SECONDS` | `30` | 2 |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `20` | 2 |
| `LLM_MAX_RETRIES` | `1` | 2 |
| `LLM_JSON_MODE` | `true` | 2 |
| `LLM_REASONING_EFFORT` | `low` | 2 |
| `HTTP_USER_AGENT` | `SentimentPulse/1.1 (+research)` | 3 |
| `INGESTION_TIMEOUT_SECONDS` | `20` | 3 |
| `YF_NEWS_COUNT` | `50` | 3 |
| `FEED_RETRY_ATTEMPTS` | `2` | 3 |
| `FINBERT_BATCH_SIZE` | `16` | 3 |
| `FINBERT_PRELOAD` | `true` | 3 |
| `FINBERT_TORCH_THREADS` | `0` (torch default) | 3 |
| `MAX_CONCURRENT_PIPELINES` | `2` | 3 |
| `JOB_QUEUE_TIMEOUT_SECONDS` | `120` | 3 |
| `SSE_HEARTBEAT_SECONDS` | `15` | 3 |
| `RATE_LIMIT_READ_PER_MINUTE` | `120` | 3 |
| `TRUSTED_PROXY_IPS` | `[]` | 3 |
| `API_KEY` | `""` (off) | 3 |
| `PUBLIC_HISTORY` | `true` | 3 |
| `LLM_DAILY_BUDGET_USD` | `1.00` | 3 |
| `RUN_RETENTION_DAYS` | `30` | 3 |
| `RUN_MIGRATIONS_ON_STARTUP` | `true` | 3 |

**Changed:** `LLM_FALLBACK_MODEL_ID` defaults to `nvidia/nemotron-3-super-120b-a12b:free` (previously hardcoded in the service); `DATABASE_URL` and `.env` resolve against the project root; `MODEL_PRICING` refreshed and env-overridable; `APP_HOST` / `APP_PORT` used by `python -m app`; `MAX_PROMPT_TOKENS` enforced.

**Removed:** `MAX_EXCERPT_TOKENS`.

---

## 12. Test strategy and verification commands

**New or rewritten test modules**
- Backend:
  - shared: `tests/conftest.py`, `tests/fakes.py`;
  - contract and e2e: `tests/contract/test_openapi_snapshot.py`, `tests/contract/test_sse_contract.py`, `tests/e2e/test_job_flow.py`;
  - decision logic: `tests/unit/test_relevance.py`, `test_corroboration.py`, `test_ticker_resolution.py`, `test_session_window.py`, `test_llm_service.py`;
  - ingestion and scoring: `tests/unit/test_news_service.py`, `test_scoring.py`;
  - platform: `tests/unit/test_rate_limiter.py`, `test_job_manager.py`, `test_maintenance.py`, `test_config.py`, `test_db_types.py`;
  - migrations: `tests/integration/test_migrations.py`.
- Frontend (Vitest): `api.ts`, time formatters, `LoadingStepper`, `EvidenceExplorer`, `RationaleSection`.

**Commands**
```bash
# Backend (every phase)
pip install -r requirements-dev.txt
ruff check .
python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=85
python -m pytest -m slow     # real FinBERT (cached model)
python -m pytest -m live     # real feeds; opt-in, needs network

# Migrations against a throwaway DB (PowerShell: $env:DATABASE_URL = "...")
DATABASE_URL=sqlite:///./tmp/check.db alembic upgrade head
DATABASE_URL=sqlite:///./tmp/check.db alembic check

# Frontend (needs Node 20)
cd frontend
npm ci && npm run gen:api && npm run typecheck && npm run lint && npm test && npm run build
```

---

## 13. Manual smoke-test checklist (end of Phases 1, 2 and 3)

1. Start the server (`python -m uvicorn app.main:app`; `python -m app` from Phase 3): startup and access logs visible.
2. Fresh AAPL run: the stepper walks through all six stages with real percentages; the result shows `MISS`; repeating shows the cached badge.
3. Forced failure (simulated feed outage or bad LLM config): the UI shows the backend's message; no 404.
4. EUR/USD: the evidence includes headlines that name "EUR/USD".
5. GC=F and BTC-USD complete with relevant evidence.
6. `$GOLD` then `GOLD` resolve to different assets; `ZZQXV` → "not found" message.
7. Network off: a 503 or a `DEGRADED` result with a clear message.
8. History shows correct local dates/times; the session banner's ET row shows ET.
9. Same ticker in two tabs: one job (`coalesced`).
10. 16 rapid analyses: 429 with the retry time shown.

---

## 14. Traceability matrix

| Finding | Task(s) |
|---|---|
| C1 | P1.1, P1.2 |
| C2 | P1.3 |
| C3 | P2.2 |
| C4 | P2.1 |
| H1 | P0.1, P0.2 |
| H2 | P0.3 |
| H3 | P2.3 |
| H4 | P2.2 |
| H5 | P2.3 |
| H6 | P2.5 |
| H7 | P2.5 |
| H8 | P3.2 |
| H9 | P3.1 |
| H10 | P1.8 |
| H11 | P3.3 |
| H12 | P3.5 |
| H13 | P1.4 |
| H14 | P2.4 |
| H15 | P3.4, P3.6 |
| H16 | P3.7 |
| H17 | P0.1 |
| M1 | P1.6 |
| M2 | P1.5, P1.6 |
| M3 | P1.6, P2.1 |
| M4 | P1.6 |
| M5 | P1.6 |
| M6 | P1.2 |
| M7 | P3.4 |
| M8 | P3.4 |
| M9 | P1.7 |
| M10 | P1.6, P2.5, P3.1 |
| M11 | P2.1 |
| M12 | P2.6 |
| M13 | P2.4 (buckets), P3.8 |
| M14 | P1.4, P1.5 |
| M15 | P2.2 (queries), P3.1 (dedup order) |
| M16 | P2.3 (TTL cache), P3.2 (mock), P4.1 |
| M17 | P0.4, P2.5 (pricing) |
| M18 | P2.7, P4.3 |
| L1 | P4.2 |
| L2 | P1.8 |
| L3 | P1.4 (columns), P3.6 (input) |
| L4 | P1.4 (fact IDs), P4.6 |
| L5 | P2.4 |
| L6 | P3.4 |
| L7 | P0.4 (ini), P3.8 (env.py) |
| L8 | P4.4 |
| L9 | P0.4 (CI), P4.5 |
| L10 | P3.1, P3.6 |

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Relevance, corroboration and window changes shift verdicts (more HOLDs, different BUY/SELL) | Intended. Table tests plus a before/after comparison for AAPL, EUR/USD, GC=F and BTC-USD recorded in the Phase 2 PR; the `ALGORITHM_VERSION` bump invalidates old cache entries. |
| Longer windows (D1) mean more articles to score before batching lands | `MAX_RETAINED_ARTICLES` (350) still caps the work; Phase 3 follows directly. |
| Migrations on your existing database | Backup first; each migration has a tested downgrade and backfill. |
| `response_format` / `reasoning` not supported by every OpenRouter model | Automatic retry without them; live manual check for each configured model. |
| Windows specifics (time-machine, socket guard, paths) | Verified first in Phase 0 on this machine; CI covers Linux. |
| Yahoo / Google behaviour changes | Null-safe parsing, outcome classification, opt-in live tests. |
| Frontend work blocked without Node | Prerequisite in §0; backend tasks can proceed meanwhile. |
| Large PRs are hard to review | One PR per phase, commits per task, golden snapshot before refactors. |

---

## 16. Out of scope

Distributed workers or external job queues (Redis, Celery); PostgreSQL production support beyond keeping migrations portable; user accounts and roles (only the optional API key); calibration or back-testing of thresholds; resolving Google News redirect links to publisher URLs; adding paid news APIs.

---

## Appendix A — Findings reference

| ID | Summary |
|---|---|
| C1 | Progress event names, stages and scale differ between server and UI; `failed` unhandled |
| C2 | Runs aren't saved when all RSS feeds fail, but the job points at them → 404 |
| C3 | Forex relevance rejects pair-named headlines and accepts generic dollar/euro ones |
| C4 | Corroboration counts publishers from both sides |
| H1 | Tests write to the real database |
| H2 | Alembic logging setup silences app and Uvicorn logs |
| H3 | A `$` lookup poisons the ticker cache; the job loses the `$` intent |
| H4 | Equity/commodity relevance gaps (common-word tickers, no aliases) |
| H5 | Unknown tickers resolve instead of returning 404 |
| H6 | LLM timeouts/retries exceed the pipeline timeout; hardcoded fallback; client leak |
| H7 | Malformed or empty LLM output counted as success |
| H8 | FinBERT unbatched, double tokenisation, cold load inside the job |
| H9 | Ingestion partly sequential; no overall timeout or User-Agent; only 10 Yahoo items; HTML counted as success |
| H10 | Yahoo parser crashes on `clickThroughUrl: null` |
| H11 | Blocking DB calls in async code |
| H12 | Shared rate-limit bucket, spoofable XFF, no `Retry-After` |
| H13 | Article IDs rewritten on save; reloads always report `HIT` |
| H14 | Weekday window starts at midnight ET |
| H15 | No global concurrency cap or protection for costly operations |
| H16 | Unbounded evidence storage, no retention |
| H17 | Network/time-dependent tests, broken slow test, empty live test |
| M1 | "ET" row shows UTC |
| M2 | History timestamps without timezone |
| M3 | Misleading hero labels and counts |
| M4 | Evidence filters and counts disagree with the backend |
| M5 | LLM summary never shown; facts lack metadata |
| M6 | Polling fallback too short and not cancellable |
| M7 | SSE fixed 120 s cap, per-client polling, no heartbeat |
| M8 | "Coalescing" is just serialisation |
| M9 | Two error formats, leaked internals, misleading health check |
| M10 | Wrong metric semantics |
| M11 | Inferred publishers count toward corroboration |
| M12 | Irrelevant-only runs marked "OK"; HOLD confidence floor; arbitrary ceilings |
| M13 | CWD-relative paths, migrations per worker, cache-hash gaps, buckets > 60 min |
| M14 | Naive DateTime columns; schema length drift |
| M15 | Restrictive Google queries; title dedup before the freshness filter |
| M16 | God-function orchestrator, mock in production code, caches without TTL |
| M17 | Unpinned/unused dependencies, stale pricing |
| M18 | README, old plan and `.env.example` out of date |
| L1 | Dead code and stale messages |
| L2 | Garbled `FreshnessViolationException` message |
| L3 | No ticker length limit; narrow ticker columns |
| L4 | Fact ID collisions, overwritten retrieval time, recomputed session window |
| L5 | No early closes or special closures |
| L6 | Lock dictionary grows forever; import-time lock |
| L7 | Alembic deprecation warning; env.py URL hack |
| L8 | Frontend accessibility, CSS, fonts, labels and types polish |
| L9 | No CI/lint/Docker; bundle drift; stale files; broad `.gitignore` |
| L10 | Feed URLs not scheme-validated |
