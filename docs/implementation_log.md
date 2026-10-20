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
| P1.1 | One backend↔frontend contract | C1 | todo | |
| P1.2 | Robust frontend job client | C1, M6 | todo | |
| P1.3 | Always persist results; caching becomes a flag | C2 | todo | |
| P1.4 | Stable article IDs, truthful cache status | H13, L3, L4, M14 | todo | |
| P1.5 | Timezone-aware timestamps end to end | M2, M14 | todo | |
| P1.6 | Truthful UI | M1–M5, M10 | todo | |
| P1.7 | Unified errors and an honest health check | M9 | todo | |
| P1.8 | Hotfixes | H10, L2 | todo | |
| P1.9 | Rebuild and commit the bundle | D4 | todo | |
| P2.1 | Corroboration by direction | C4, M11, M3 | todo | |
| P2.2 | Relevance engine rebuild | C3, H4, M15 | todo | |
| P2.3 | Ticker resolution | H3, H5, M16 | todo | |
| P2.4 | Session window and market calendar | H14, L5, M13 | todo | |
| P2.5 | LLM robustness | H6, H7, M10, M17 | todo | |
| P2.6 | Data status, HOLD reasons, confidence | M12 | todo | |
| P2.7 | Documentation for Phase 2 behaviour | M18 | todo | |
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

## Deviations

_None._

## Follow-ups

_None._
