# Remediation Plan: SentimentPulse Defect Findings (F-01 to F-19)

---

## 1. Goal Description

Remediate all 19 findings (F-01 through F-19) identified in the independent review of commit `888baf0` across the Market-Sentiment ("SentimentPulse") codebase. The platform is an empirical market sentiment intelligence engine featuring a FastAPI backend (`app/`), SQLite/Alembic persistence (`app/db/`, `alembic/`), local FinBERT NLP inference (`app/services/finbert_service.py`), an optional OpenRouter LLM catalyst audit (`app/services/llm_service.py`), and a React 19 + TypeScript frontend (`frontend/`, compiled into `app/static/`).

Its core purpose is a directional sentiment verdict (**BUY**, **HOLD**, **SELL**) for the **CURRENT DAY'S** news, anchored strictly to the `SessionWindow` computed in `app/core/session_window.py`.

### The Core Invariant (Enforced in Phase 1)
Every article reaching FinBERT, the LLM, or `AggregatorService` must possess a trusted timestamp inside `[window_start_utc, window_end_utc]`, allowing at most 5 minutes of future clock skew. This invariant will be enforced in code, verified immediately before aggregation with an explicit domain assertion raising `FreshnessViolationException`, and covered by rigorous regression tests.

---

## 2. User Review Required

> [!IMPORTANT]
> **1. Core Freshness Invariant & Domain Assertion**:
> Ingestion will no longer default missing or unparsed timestamps to `now()`. Missing timestamps become `None`. Articles with missing timestamps (`MISSING_OR_UNTRUSTED_TIMESTAMP`) or timestamps outside the session window (`TIMESTAMP_OUT_OF_WINDOW`) will be excluded before relevance filtering and FinBERT scoring. An explicit pre-aggregation check in `AnalysisOrchestrator` will raise `FreshnessViolationException` if any out-of-window article bypasses filters.
>
> **2. Two-Publisher Corroboration Rule (F-09)**:
> `BUY` and `SELL` verdicts strictly require at least two distinct, known canonical publishers among directional articles (excluding `"Unknown Aggregator"` and inferred publishers). If only a single publisher provides directional news, the verdict is forced to `HOLD` with warning code `INSUFFICIENT_CORROBORATION`. The existing test `test_single_publisher_warning_emitted_without_false_hold_block` (which asserted `BUY`) will be updated to assert `HOLD` and reported in the final report.
>
> **3. Database Migration 002 & SQLite Consistency**:
> New columns (`data_status`, `llm_summary` on `analysis_runs`; `effective_weight`, `age_hours` on `article_evidence`; making `published_at_utc` nullable) will be packaged in Alembic migration `002_freshness_reliability_schema.py`. The SQLite startup path (`Base.metadata.create_all`) will be kept synchronized.

---

## 3. Mapping of Findings to Phases, Files, and Functions

| Finding ID | Severity | Phase | Target File(s) | Target Function(s) / Components |
|---|---|---|---|---|
| **F-01** | **Critical** | Phase 1 | `app/core/models.py`<br>`app/services/news_service.py` | `IngestedArticle.published_at_utc`<br>`NewsService._fetch_yfinance_news_sync`<br>`NewsService._fetch_google_rss_source_sync`<br>`NewsService._fetch_direct_rss_sync` |
| **F-06** | **High** | Phase 1 | `app/services/news_service.py` | `NewsService._fetch_google_rss_source_sync`<br>`NewsService.fetch_news_for_session`<br>`NewsService._clean_html` |
| **F-07** | **Critical** | Phase 1 | `app/core/session_window.py`<br>`app/services/deduplication_service.py`<br>`app/services/orchestrator.py`<br>`app/core/exceptions.py`<br>`app/core/models.py` | `SessionWindow.is_timestamp_in_window`<br>`DeduplicationService.filter_by_session_window`<br>`AnalysisOrchestrator.run_pipeline`<br>`FreshnessViolationException`<br>`AnalysisResult.data_status` |
| **F-08** | **High** | Phase 1 | `app/services/aggregator_service.py`<br>`app/core/models.py` | `AggregatorService.aggregate_and_decide`<br>`ScoredArticle.effective_weight`<br>`ScoredArticle.age_hours` |
| **F-02** | **High** | Phase 2 | `app/main.py`<br>`app/db/database.py` | `lifespan`<br>`get_db`<br>`Base.metadata.create_all` |
| **F-03** | **High** | Phase 2 | `app/core/session_window.py`<br>`app/api/routes.py`<br>`app/services/orchestrator.py`<br>`app/db/repository.py` | `compute_session_bucket`<br>`analyze_ticker`<br>`AnalysisOrchestrator.run_pipeline`<br>`SentimentRepository.get_cached_run` |
| **F-04** | **High** | Phase 2 | `app/services/news_service.py`<br>`app/core/exceptions.py`<br>`app/services/orchestrator.py` | `NewsService._fetch_direct_rss_sync`<br>`NewsService._fetch_google_rss_source_sync`<br>`NewsUnavailableException`<br>`AnalysisOrchestrator.run_pipeline` |
| **F-14** | **High** | Phase 2 | `app/api/routes.py`<br>`app/services/orchestrator.py`<br>`app/services/finbert_service.py`<br>`app/config.py` | `analyze_ticker`, `run_background_job`, `stream_job_events`<br>`FinBERTService._ensure_model_loaded`<br>`PIPELINE_TIMEOUT_SECONDS` |
| **F-05** | **High** | Phase 3 | `app/services/deduplication_service.py`<br>`.env.example` | `DeduplicationService.process_and_deduplicate`<br>Environment defaults synchronization |
| **F-09** | **Critical** | Phase 3 | `app/services/aggregator_service.py` | `AggregatorService.aggregate_and_decide`<br>Two-publisher corroboration & warning code |
| **F-10** | **High** | Phase 3 | `app/services/deduplication_service.py` | `DeduplicationService.is_materially_relevant`<br>Word-boundary regexes & corporate token filtering |
| **F-11** | **High** | Phase 3 | `app/services/deduplication_service.py` | `DeduplicationService.normalize_publisher`<br>Whole-word matching & Yahoo - X normalization |
| **F-12** | **High** | Phase 3 | `app/services/finbert_service.py`<br>`README.md` | `FinBERTService._batch_score_articles_sync`<br>Neutral dominance removal & weight formula |
| **F-13** | **High** | Phase 3 | `app/services/llm_service.py`<br>`app/config.py`<br>`app/core/enums.py`<br>`app/core/models.py` | `LLMService.verify_and_synthesize`<br>`LLMService._parse_llm_response`<br>`LLM_FALLBACK_MODEL_ID`<br>`AnalysisResult.llm_summary` |
| **F-15** | **Medium/High** | Phase 4 | `app/api/dependencies.py`<br>`app/main.py`<br>`app/utils/rate_limiter.py` | `get_client_ip`<br>`CORSMiddleware`<br>`SlidingWindowRateLimiter.check` |
| **F-16** | **Medium/High** | Phase 4 | `app/services/ticker_service.py` | `TickerService.validate_and_resolve`<br>`TickerService.format_yf_ticker`<br>`TickerService.normalize_ticker` |
| **F-17** | **Medium** | Phase 4 | `app/services/orchestrator.py`<br>`frontend/src/types.ts`<br>`frontend/src/components/*` | `ScoredArticle.lead_text`<br>`EvidenceExplorer.tsx`<br>`DecisionHero.tsx`<br>`RationaleSection.tsx` |
| **F-18** | **Medium** | Phase 4 | `app/config.py`<br>`app/api/routes.py`<br>`app/main.py`<br>`README.md` | Configuration pruning, rate limiting endpoints, and documentation sync |
| **F-19** | **High** | Phase 5 | `pytest.ini`<br>`tests/unit/*`<br>`tests/integration/*` | Strict markers (`live`, `slow`), new test suites, >80% news_service, >85% overall coverage |

---

## 4. Phase-by-Phase Proposed Changes

### Phase 1: Freshness (F-01, F-06, F-07, F-08)

#### 1. IngestedArticle Timestamp Optionality (F-01)
- **Files**: `app/core/models.py`, `app/services/news_service.py`
- In `app/core/models.py`, change:
  ```python
  published_at_utc: datetime | None = None  # None = missing or untrusted
  ```
- In `news_service.py`, parse timestamps strictly without defaulting to `now()`:
  - **yfinance**: Check `item["content"]["pubDate"]` (ISO-8601 with Z). If present, parse with `datetime.fromisoformat(ts.replace("Z", "+00:00"))`. Fall back to `item.get("providerPublishTime")` as UNIX timestamp. If neither exists or parsing errors, set `published_at_utc = None`.
  - **Google & Direct RSS**: Parse `entry.published_parsed` to UTC datetime. If missing or invalid, set `published_at_utc = None`.

#### 2. yfinance Parser Current Payload & Real Publisher (F-01)
- **File**: `app/services/news_service.py` (`_fetch_yfinance_news_sync`)
- Support current yfinance schema:
  - Title: `item["content"]["title"]` with fallback to `item["title"]`.
  - Summary: `item["content"]["summary"]` or `description` with fallback to `item["summary"]`.
  - Link: `item["content"]["canonicalUrl"]["url"]` or `clickThroughUrl["url"]` with fallback to `item["link"]`.
  - Publisher: `item["provider"]["displayName"]` with fallback to `item.get("publisher", "Yahoo Finance")`.

#### 3. Google RSS Scraper Query Bounding & Source Parsing (F-06)
- **File**: `app/services/news_service.py` (`_fetch_google_rss_source_sync`, `fetch_news_for_session`, `_clean_html`)
- Bound query at source: Compute `N = min(72, math.ceil(session.window_duration_hours) + 1)` and append `when:{N}h` (or `when:{N}d`).
- Query format: Construct one general query from asset name and ticker (e.g. `"Bitcoin"`, `"Gold"`, `"Apple Inc." AAPL`), plus per-publisher sweeps using `site:` operator (`site:reuters.com`, `site:bloomberg.com`, `site:cnbc.com`, `site:wsj.com`, `site:marketwatch.com`, `site:seekingalpha.com`, `site:fool.com`). Stop appending publisher names as free text.
- Extract publisher from `entry.source.title` (or `entry.source.value`). If missing, fall back to queried publisher and mark `raw_provider_metadata["publisher_inferred"] = True`. Inferred publishers never count as distinct canonical publishers.
- Strip trailing `" - <Publisher>"` from title if it matches entry source.
- Drop summary if, after HTML stripping, case, and whitespace normalization, it equals the title or title plus publisher.

#### 4. Freshness Filtering Stage & Session Window Invariant (F-07)
- **Files**: `app/core/session_window.py`, `app/services/deduplication_service.py`, `app/services/orchestrator.py`, `app/core/exceptions.py`, `app/core/models.py`
- In `session_window.py`:
  ```python
  def is_timestamp_in_window(self, dt_utc: datetime | None) -> bool:
      if dt_utc is None:
          return False
      if dt_utc.tzinfo is None:
          dt_utc = dt_utc.replace(tzinfo=timezone.utc)
      # Allow at most 5 minutes of future clock skew
      return self.window_start_utc <= dt_utc <= (self.window_end_utc + timedelta(minutes=5))
  ```
- In `deduplication_service.py`, add `filter_by_session_window`:
  ```python
  @classmethod
  def filter_by_session_window(
      cls, articles: list[IngestedArticle], session: SessionWindow
  ) -> tuple[list[IngestedArticle], list[tuple[IngestedArticle, ExclusionReason, str]], int, int]:
  ```
  - Categorizes articles into valid in-window vs excluded (`MISSING_OR_UNTRUSTED_TIMESTAMP` or `TIMESTAMP_OUT_OF_WINDOW`).
  - Caps sample excluded articles to at most 20 per reason to prevent evidence bloat.
  - Returns true counts `(excluded_out_of_window, excluded_missing_timestamp)`.
- In `orchestrator.py`:
  - Run `filter_by_session_window` immediately after news ingestion, before relevance filtering and deduplication.
  - Populate `PipelineMetrics.excluded_out_of_window` and `PipelineMetrics.excluded_missing_timestamp`.
  - **Pre-Aggregation Assertion**: Immediately before FinBERT/Aggregator, assert every article satisfies `session.is_timestamp_in_window(a.published_at_utc)`. Raise `FreshnessViolationException` if violated.
  - When zero in-window articles survive, return `DecisionVerdict.HOLD`, `decision_confidence=0.0`, `data_status="NO_FRESH_NEWS"`, and summary: `"No articles published inside the current session window ({N} out of window, {M} undated)."`.

#### 5. Aggregator Defense-in-Depth & Effective Weight Consistency (F-08)
- **Files**: `app/services/aggregator_service.py`, `app/core/models.py`
- On `ScoredArticle`, add fields: `effective_weight: float = 0.0`, `age_hours: float = 0.0`.
- In `AggregatorService.aggregate_and_decide`:
  - Ignore and warn about any article where `not session.is_timestamp_in_window(art.published_at_utc)`.
  - Compute `effective_weight = round(recency_decay * max(0.2, art.final_weight), 4)` once per article.
  - Skip articles where `effective_weight <= 0.0`.
  - Use `effective_weight` consistently for the composite score AND directional tallies. Directional tallies must never count an article the score ignores.

---

### Phase 2: Reliability (F-02, F-03, F-04, F-14)

#### 1. SQLite Database Startup Table Initialization (F-02)
- **Files**: `app/main.py`, `app/db/database.py`, `README.md`
- In `app/main.py` lifespan:
  ```python
  if settings.DATABASE_URL.startswith("sqlite"):
      import app.db.models  # ensure models are registered on Base
      from app.db.database import Base, engine
      Base.metadata.create_all(bind=engine)
  ```
- Document `alembic upgrade head` in README for PostgreSQL and production databases.

#### 2. Unified Session Bucket & Cache TTL Enforcement (F-03)
- **Files**: `app/core/session_window.py`, `app/api/routes.py`, `app/services/orchestrator.py`, `app/db/repository.py`
- In `session_window.py`, implement single source of truth:
  ```python
  def compute_session_bucket(session: SessionWindow, now: datetime | None = None) -> tuple[str, int]:
      # REGULAR_HOURS: floored to settings.CACHE_INTRADAY_BUCKET_MINUTES
      # All other sessions: floored to settings.CACHE_OFF_MARKET_BUCKET_MINUTES
      # Returns (bucket_string, bucket_seconds)
  ```
- Use `compute_session_bucket` in both `routes.py` and `orchestrator.py`.
- In `SentimentRepository.get_cached_run(db, cache_key, max_age_seconds)`:
  - If `(now - run.created_at).total_seconds() > max_age_seconds`, treat as expired (return `None`).
  - For `data_status == "NO_FRESH_NEWS"`, set TTL to `min(bucket_seconds, 300)`.

#### 3. Provider Health Tracking & Total Outage 503 (F-04)
- **Files**: `app/services/news_service.py`, `app/core/exceptions.py`, `app/services/orchestrator.py`
- In `news_service.py`:
  - Replace `feedparser.parse(url)` with `httpx.get(url, timeout=httpx.Timeout(8.0, connect=4.0))` followed by `feedparser.parse(resp.content)`.
  - Mark outcome `FAILED` on exception, HTTP error, timeout, or feed with 0 entries; `SUCCESS` only when articles are parsed.
  - Wrap total ingestion in `asyncio.wait_for(..., timeout=settings.INGESTION_TIMEOUT_SECONDS)`.
- In `orchestrator.py`:
  - If every provider returned `FAILED`, raise `NewsUnavailableException(503)`, mark job `FAILED`, and cache nothing.

#### 4. Async Concurrency Hygiene & Lazy Loading Lock (F-14)
- **Files**: `app/api/routes.py`, `app/services/orchestrator.py`, `app/services/finbert_service.py`, `app/config.py`
- In `routes.py`:
  - Execute `TickerService.validate_and_resolve` via `await asyncio.to_thread(...)` and pass resolved `Asset` down.
  - SSE generator queries DB via `await asyncio.to_thread(SentimentRepository.get_job, db, job_id)`.
  - Retain strong references to background tasks in `BACKGROUND_TASKS: set[asyncio.Task]` with `task.add_done_callback(BACKGROUND_TASKS.discard)`.
- In `finbert_service.py`:
  - Guard model initialization with `_load_lock = threading.Lock()`.
- In `config.py`:
  - Add `PIPELINE_TIMEOUT_SECONDS: int = 90`. Wrap pipeline run in `asyncio.wait_for`.

---

### Phase 3: Decision Integrity (F-05, F-09, F-10, F-11, F-12, F-13)

#### 1. Capacity Cap Newest-First & Config Synchronization (F-05)
- **Files**: `app/services/deduplication_service.py`, `.env.example`
- In `process_and_deduplicate`, after deduplication and clustering, sort retained articles by `published_at_utc` descending (newest first) before truncating to `settings.MAX_RETAINED_ARTICLES`.
- Synchronize `.env.example` numeric values with `config.py`:
  - `MAX_RETAINED_ARTICLES=350`
  - `MAX_LLM_CANDIDATES=100`
  - `MAX_PROMPT_TOKENS=8000`
  - `MAX_COMPLETION_TOKENS=1000`
  - `MAX_COST_PER_RUN_USD=0.05`

#### 2. Two-Publisher Corroboration Rule (F-09)
- **File**: `app/services/aggregator_service.py`
- BUY or SELL strictly requires at least two distinct, known canonical publishers among directional articles.
- Exclude `"Unknown Aggregator"` and inferred publishers (`publisher_inferred is True`).
- If fewer than 2 distinct canonical publishers, return `DecisionVerdict.HOLD` with warning code `INSUFFICIENT_CORROBORATION` and an inference line.
- Update docstring. Remove the vacuous cluster check or redefine it so distinct publishers rule strictly governs corroboration.

#### 3. Entity Relevance Word Boundaries & Token Stripping (F-10)
- **File**: `app/services/deduplication_service.py` (`is_materially_relevant`)
- Use regex word-boundary checks (`\b{re.escape(token)}\b`) for all ticker and token matches.
- For 1-2 letter tickers (`T`, `ON`, `V`, `A`), require `$TICKER` or the company's distinctive name in the title.
- Strip generic company tokens: `{"platforms", "group", "holdings", "technologies", "systems", "solutions", "international", "corp", "inc", "ltd"}` so they cannot match on their own.
- For crypto, forex, and commodities, match asset name and existing pair variants.

#### 4. Canonical Publisher Whole-Word Matching & Yahoo - X (F-11)
- **File**: `app/services/deduplication_service.py` (`normalize_publisher`)
- Match whole words or phrases using regex word boundaries. "ap" matches only when the entire source name is "AP" or "Associated Press" (preventing false matches on "Capital.com", "Apple Insider", "Tapestry Blog").
- For "Yahoo - X" sources, extract X and normalize X (map entry if known, otherwise X itself, rather than returning "Yahoo Finance").

#### 5. FinBERT Neutral Dominance Removal & Weight Formula (F-12)
- **File**: `app/services/finbert_service.py` (`_batch_score_articles_sync`), `README.md`
- An article is directional when `abs(p_pos - p_neg) >= 0.15`.
- Remove `p_neu > 0.60` zeroing.
- Set `initial_weight = confidence * (1.0 - p_neu)`.
- Update README formulas to reflect this continuous weighting rule.

#### 6. LLM Prompt Injection Hardening, Catalyst Category, Output Separation & Fallback (F-13)
- **Files**: `app/services/llm_service.py`, `app/config.py`, `app/core/models.py`, `app/core/enums.py`
- Strip or escape angle-bracket tag sequences (`<...>`, `</...>`) and control characters in headlines; cap headline at 200 chars.
- Parse JSON only; delete any-integer regex fallback. Treat JSON parse failure as `FAILED`, falling back to deterministic FinBERT mode.
- Ask model for category per confirmed index drawn from `CatalystCategory` and store it on `ScoredArticle.catalyst_category`.
- Boost confirmed catalysts by 1.25x weight and leave other articles unchanged.
- Store model synthesis in `AnalysisResult.llm_summary`, never replacing the rule-based verdict summary.
- Replace hardcoded fallback model with setting `LLM_FALLBACK_MODEL_ID: str = ""` (default empty).
- Record the model that actually answered in `model_versions` and telemetry.
- Note `ExclusionReason.CATALYST_REJECTED_AS_NOISE` as unused.

---

### Phase 4: API, UI, Config and Docs (F-15, F-16, F-17, F-18)

#### 1. Security & Infrastructure (F-15)
- **Files**: `app/api/dependencies.py`, `app/main.py`, `app/utils/rate_limiter.py`, `app/config.py`
- In `config.py`: Add `TRUST_PROXY_HEADERS: bool = False`, `CORS_ORIGINS: list[str] = ["http://localhost:8000", "http://localhost:5173"]`.
- In `dependencies.py`: `get_client_ip` trusts `X-Forwarded-For` only when `TRUST_PROXY_HEADERS` is True.
- In `main.py`: Set `CORSMiddleware.allow_origins = settings.CORS_ORIGINS`. Never combine wildcard with credentials.
- In `rate_limiter.py`: Prune expired and empty keys from memory dictionary.

#### 2. Ticker Resolution 404, Network Resilience & $ Prefix Bypass (F-16)
- **File**: `app/services/ticker_service.py`
- When yfinance returns no instrument / empty `quoteType`, raise `TickerNotFoundException` (404).
- When yfinance network lookup fails, log warning and continue with basic resolution.
- If ticker starts with `$`, strip `$` and bypass commodity/crypto aliases, resolving `$GOLD` and `$CORN` as listed equities. Document in README.

#### 3. UI Evidence Transparency & Freshness Display (F-17)
- **Files**: `frontend/src/types.ts`, `frontend/src/components/EvidenceExplorer.tsx`, `frontend/src/components/DecisionHero.tsx`, `frontend/src/components/RationaleSection.tsx`
- Types: Update `AnalysisResult`, `ScoredArticle`, `PipelineMetrics`.
- In `EvidenceExplorer.tsx`:
  - Show original cleaned lead text (up to 500 chars). Keep FinBERT tokenizer text private.
  - Sort evidence list newest first.
  - Display relative age ("3h ago") next to timestamp.
  - Display `effective_weight` with recency decay visual indicator.
  - Display canonical publisher separately from raw provider tag.
  - Collapsible "Excluded Articles" section grouped by exclusion reason with counts.
  - Add banner for `NO_FRESH_NEWS` stating out-of-window and undated exclusion counts.
- In `RationaleSection.tsx`:
  - Render `llm_summary` in its own distinct labeled card ("LLM Catalyst Synthesis").
- Build: Run `npm run build` in `frontend/` and commit updated `app/static/` bundle.

#### 4. Config Pruning, Endpoint Rate Limiting & Documentation Sync (F-18)
- **Files**: `app/config.py`, `.env.example`, `app/api/routes.py`, `app/main.py`, `README.md`
- Remove `FINNHUB_API_KEY`, `MAX_PROMPT_TOKENS`, `MAX_EXCERPT_TOKENS`, `SECRET_KEY`.
- Apply `settings.RATE_LIMIT_JOBS_PER_MINUTE` to `/jobs/{job_id}` and `/jobs/{job_id}/events`.
- Correct FastAPI description in `main.py` to universal multi-asset.
- Document Core Freshness Invariant, Cache TTL rules, Corroboration Rule, Neutral rule, and `$TICKER` syntax in `README.md`.

#### 5. Database Migration 002
- **Files**: `alembic/versions/002_freshness_reliability_schema.py`, `app/db/models.py`
- Add Alembic migration 002:
  - Add `analysis_runs.data_status` (String(20), default "OK").
  - Add `analysis_runs.llm_summary` (Text, nullable).
  - Add `article_evidence.effective_weight` (Float, default 0.0).
  - Add `article_evidence.age_hours` (Float, default 0.0).
  - Alter `article_evidence.published_at_utc` to nullable.
- Synchronize `app/db/models.py` with this schema.

---

### Phase 5: Tests & Coverage Expansion (F-19)

#### 1. Test Markers
- In `pytest.ini`: Register `live` and `slow` markers with default `addopts = -v --strict-markers -m "not live and not slow"`.

#### 2. Regression Tests for Critical and High Findings
- **F-01 [Critical]**: `tests/unit/test_freshness.py::test_yfinance_parser_current_and_legacy_schema`, `tests/unit/test_freshness.py::test_parsers_never_default_timestamp_to_now`
- **F-06 [High]**: `tests/unit/test_freshness.py::test_google_rss_query_bounding_and_source_extraction`, `tests/unit/test_freshness.py::test_summary_dropped_when_equals_title_or_publisher`
- **F-07 [Critical]**: `tests/unit/test_freshness.py::test_filter_by_session_window_excludes_old_and_undated`, `tests/unit/test_freshness.py::test_core_freshness_invariant_pre_aggregation_assertion_fires`, `tests/integration/test_freshness_orchestrator.py::test_btc_usd_historical_run_returns_no_fresh_news`
- **F-08 [High]**: `tests/unit/test_aggregator.py::test_aggregator_ignores_out_of_window_articles_defense_in_depth`, `tests/unit/test_aggregator.py::test_aggregator_tallies_use_effective_weight_consistently`
- **F-02 [High]**: `tests/unit/test_reliability.py::test_sqlite_startup_creates_missing_tables_and_health_passes`
- **F-03 [High]**: `tests/unit/test_reliability.py::test_compute_session_bucket_intraday_and_off_market`, `tests/unit/test_reliability.py::test_cache_ttl_expiration_enforced`, `tests/unit/test_reliability.py::test_no_fresh_news_cache_ttl_capped_at_five_minutes`
- **F-04 [High]**: `tests/unit/test_reliability.py::test_provider_health_tracking_records_failed_on_empty_or_error`, `tests/unit/test_reliability.py::test_total_provider_outage_raises_503_and_fails_job_without_caching`
- **F-14 [High]**: `tests/unit/test_reliability.py::test_async_hygiene_background_task_strong_reference`, `tests/unit/test_reliability.py::test_finbert_thread_safe_lazy_loading`
- **F-05 [High]**: `tests/unit/test_decision_integrity.py::test_capacity_cap_retains_newest_articles_first`, `tests/unit/test_decision_integrity.py::test_env_example_matches_config_defaults`
- **F-09 [Critical]**: `tests/unit/test_aggregator.py::test_single_publisher_positive_forces_hold_with_insufficient_corroboration`, `tests/unit/test_aggregator.py::test_multi_publisher_positive_triggers_buy`
- **F-10 [High]**: `tests/unit/test_deduplication.py::test_table_driven_relevance_short_tickers_and_generic_tokens`
- **F-11 [High]**: `tests/unit/test_deduplication.py::test_publisher_normalization_whole_word_and_yahoo_x`
- **F-12 [High]**: `tests/unit/test_finbert_scoring.py::test_directional_article_with_high_neutral_preserves_signal`, `tests/unit/test_finbert_scoring.py::test_neutral_weighting_formula`
- **F-13 [High]**: `tests/unit/test_llm_service.py::test_prompt_injection_angle_brackets_escaped`, `tests/unit/test_llm_service.py::test_malformed_json_triggers_failed_and_deterministic_fallback`, `tests/unit/test_llm_service.py::test_llm_summary_never_replaces_rule_verdict`
- **F-15 [Medium/High]**: `tests/e2e/test_api_security.py::test_client_ip_proxy_trust`, `tests/e2e/test_api_security.py::test_cors_origins_and_credentials`, `tests/unit/test_rate_limiter.py::test_prune_expired_and_empty_keys`
- **F-16 [Medium/High]**: `tests/unit/test_ticker_service.py::test_missing_instrument_raises_404_not_found`, `tests/unit/test_ticker_service.py::test_dollar_prefix_bypasses_commodity_aliases`

#### 3. Live & Slow Tests
- `@pytest.mark.live`: `tests/integration/test_live_and_slow.py::test_live_feeds_aapl_btc_eurusd` (AAPL, BTC-USD, EUR/USD against real feeds; every retained article inside session window).
- `@pytest.mark.slow`: `tests/integration/test_live_and_slow.py::test_slow_real_finbert_classification` (Loads real FinBERT on CPU and classifies positive and negative headlines).

---

## 5. Verification Plan

### Automated Execution
```bash
# 1. Base test suite run after each phase
python -m pytest

# 2. Coverage threshold verification
python -m pytest --cov=app --cov-report=term
# Verification thresholds: news_service.py > 80%, overall app > 85%

# 3. Live suite validation (opt-in)
python -m pytest -m "live"

# 4. Slow suite validation (opt-in)
python -m pytest -m "slow"

# 5. Frontend bundle compilation
cd frontend && npm run build
```

### Git Commit Strategy
One atomic commit per phase naming the finding IDs:
- Phase 1: `fix(freshness): enforce session window filtering, parser freshness, and effective weights (F-01, F-06, F-07, F-08)`
- Phase 2: `fix(reliability): ensure startup table creation, cache TTL, provider health, and async hygiene (F-02, F-03, F-04, F-14)`
- Phase 3: `fix(decision): enforce corroboration, capacity ordering, word boundaries, neutral rule, and LLM hardening (F-05, F-09, F-10, F-11, F-12, F-13)`
- Phase 4: `fix(api-ui): update proxy security, ticker 404, evidence UI, config cleanup, and docs (F-15, F-16, F-17, F-18)`
- Phase 5: `test(coverage): expand test suite with regression tests and register live/slow markers (F-19)`
