# UI v2 Deviations Log

This file tracks design and implementation decisions, edge cases, and any deviations from `docs/sentiment-pulse-spec-sheet-rebuild-plan.md`.

## Phase 0: Baseline and Screenshot Harness
- **Deviations**: None.
- **Notes**:
  - Created `frontend/tests/visual/fixtures.ts` providing typed `AnalysisResult` fixtures matching `types.ts` schemas for:
    - BUY (corroborated with 13 articles, 1 without URL, 1 undated, 0 negative for filter-empty state).
    - HOLD / NO_FRESH_NEWS.
    - SELL / DEGRADED.
    - Result with `llm_summary` and structured observed facts.
    - Result with excluded articles in 2 reasons (`TIMESTAMP_OUT_OF_WINDOW` and `INSUFFICIENT_ENTITY_RELEVANCE`).
  - Created `frontend/tests/visual/states.spec.ts` mocking API endpoints (`/api/v1/health`, `/api/v1/history`, `/api/v1/analyze`, and background job events) to capture full-page screenshots across all 9 required states at 4 viewports (1440x900, 1024x768, 768x1024, 375x812).
  - Executed harness without a backend running and produced 36 "before" baseline screenshots in `frontend/tests/visual/__out__/before/`.
  - Added `__out__/` and `test-results/` to `.gitignore`.

## Phase 1: Foundations and Frame
- **Deviations**: None.
- **Notes**:
  - Installed `@fontsource/inter-tight` (600, 700, 800) and imported in `main.tsx`.
  - Renamed `styles/index.css` to `styles/legacy.css`, replaced `:root` and global resets with a light-theme compat mapping layer and removed deleted container/header rules.
  - Created modular stylesheets: `tokens.css`, `base.css`, `primitives.css`, `frame.css`, `landing.css`, `motion.css`, `responsive.css`, and a new master `index.css`.
  - Rebuilt `Header.tsx` (black legal disclaimer strip + sticky top nav with ET/UTC clocks, no icons/blur/shadow).
  - Added `SectionRail.tsx` (7-step numbered navigation with MutationObserver and IntersectionObserver, fully guarded for jsdom compatibility).
  - Added `LandingHero.tsx` (spec sheet welcome card with CROX-style system status DL table).
  - Added `SiteFooter.tsx` (static black slab footer).
  - Updated `App.tsx` layout structure to `.sp-app` > `Header` > `.sp-page` > `.sp-rail` + `.sp-main` > `SiteFooter`, with `.sp-error` alert block.
  - Added test suites `SectionRail.test.tsx` and `LandingHero.test.tsx`.

## Phase 2: Input, Loading, Context
- **Deviations**: None.
- **Notes**:
  - Created `frontend/src/styles/input.css` implementing Section 7.4 `#search-section.sp-input.sp-sheet`, `.sp-sec-head`, `.sp-input-main`, `.sp-input-form`, `.sp-input-field` (borderless, 3px solid ink underline, uppercase display font, caret orange, placeholder `--sp-rule`), `.sp-btn--xl`, `.sp-chip-strip` (grid with min 3.5rem chips and hover inversion), and `.sp-options` with custom 20px `.sp-toggle-box` and focus rings.
  - Created `frontend/src/styles/loading.css` implementing Section 7.5 `#analysis-stepper.sp-loading.sp-sheet`, `.sp-loading-top`, giant `.sp-counter` display, 20px `.sp-ruler` progress bar with tick background and orange fill, `.sp-loading-msg`, `.sp-stages` 6-cell grid, and active stage tag 1Hz blinking square (`::before`). Spinners completely removed.
  - Created `frontend/src/styles/context.css` implementing Section 7.6 `#session-window-banner.sp-context.sp-sheet`, 6-cell spec strip, solid green square for `OPEN (RTH)` and hollow ink square on hatch background for `CLOSED`.
  - Rebuilt `SearchBar.tsx`, `LoadingStepper.tsx`, and `SessionWindowBanner.tsx` matching all spec sheet v2 markup and class names, preserving all state, handlers, props, and contract IDs/classes (`form.search-form`).
  - Removed migrated search, stepper, and session banner rules from `frontend/src/styles/legacy.css`.
  - Added unit test suites `SearchBar.test.tsx`, `LoadingStepper.test.tsx`, and `SessionWindowBanner.test.tsx` (all passing).
  - Rebuilt production static bundle in `app/static/`.

## Phase 3: Signal
- **Deviations**: None.
- **Notes**:
  - Created `frontend/src/styles/signal.css` implementing Section 7.7 `#decision-hero-card.sp-signal`, `.sp-sec-head.sp-signal-head`, `.sp-signal-main` 12-column grid (8 / 4 split on desktop), `.sp-signal-id` containing `#result-ticker-symbol` (with `data-len="long"` for tickers over 8 characters, `overflow-wrap: anywhere`), `.sp-company`, and `.sp-tags`.
  - Rebuilt `.sp-verdict` as a slab cell: BUY in `--sp-buy` (solid green), SELL in `--sp-sell` (solid red), and HOLD in black slab with hatch pattern (`--sp-hatch-on-slab`).
  - Implemented `.sp-notice` warning and caution banners (1px ink border, hatch background, 6px ink or `--sp-sell` left bar).
  - Implemented `.sp-metrics` 4-cell spec grid (`2fr 1fr 1fr 1fr` on desktop, `1fr 1fr` on tablet, `1fr` on mobile):
    - Wide Composite Sentiment cell with `.sp-score` (`is-pos`, `is-neg`, `is-flat` classes with zero inline color styles), 28px tick gauge with hatch zone and marker (`left` mapped accurately to score from 0% to 100%), and mono scale labels.
    - Confidence Level cell with 10-segment meter (`.sp-seg`).
    - Evidence Quality cell with 10-segment meter and retained articles count.
    - Publisher Corroboration cell with exact corroboration strings (`Corroborated`, `Uncorroborated`, `Single Publisher`, `Insufficient Corroboration`).
  - Preserved the legal and heuristic footnote in a black slab cell directly under metrics with new static tag `Research use only` (without the word "corroborated").
  - Removed migrated Decision Hero styles and media queries from `frontend/src/styles/legacy.css`.
  - Added new test cases to `DecisionHero.test.tsx` verifying `data-len="long"`, gauge marker `left` at 0%, 50%, and 100%, and composite tone classes `is-pos`, `is-neg`, and `is-flat`. All 12 tests passed.
  - Rebuilt production static bundle in `app/static/`.

## Phase 4: Rationale and Evidence
- **Deviations**: None.
- **Notes**:
  - Created `frontend/src/styles/rationale.css` implementing Section 7.8 `#rationale-section.sp-rationale`, `.sp-sec-head`, optional `#llm-synthesis-card.sp-sheet.sp-llm` catalyst synthesis card, `.sp-rationale-grid` split ledger, `.sp-pull` directional summary (rendered once without duplicate titles), `.sp-ledger` numbered inference list with padded numbers (`01`, `02`), and `.sp-facts` observed facts list with publisher citation, UTC timestamp, catalyst category tag, and directional impact badges (`▲ POSITIVE`, `▼ NEGATIVE`, `■ NEUTRAL`).
  - Created `frontend/src/styles/evidence.css` implementing Section 7.9 `#evidence-explorer.sp-evidence`, 4 filter tabs (`.filter-tab.sp-filter-tab`) with 3px solid `--sp-orange` bottom border when active (`.active`), `.sp-empty-filter` hatch box, `#evidence-articles-list.sp-ledger-table` with table head, presentational `.sp-row.evidence-item` with hover inversion (black background / white text / inverted link & toggle), tri-segment FinBERT bar (`.sp-tri` with positive, neutral, negative proportional widths and directional tone `is-pos`/`is-neg`/`is-flat`), detail drawer with lead text and percentage breakdown, and `.sp-excluded-wrap` accordion with hatch container, group tags, and show/hide toggle.
  - Extracted `frontend/src/components/EvidenceRow.tsx` presentational component with local expand/collapse `useState`, full test contract classes (`.evidence-item`, `.article-title-link`, `.article-title-text`), tri-segment bar, and detail drawer.
  - Rebuilt `frontend/src/components/RationaleSection.tsx` and `frontend/src/components/EvidenceExplorer.tsx` to match spec sheet v2 structure with zero inline styles.
  - Removed migrated rationale, evidence, and filter tab rules and responsive overrides from `frontend/src/styles/legacy.css`.
  - Added unit test suites `RationaleSection.test.tsx` (7 tests) and `EvidenceExplorer.test.tsx` (7 tests), covering summary uniqueness, inferences ledger, observed facts impact badges, LLM synthesis card, partition filter counts and filtering, row expand/collapse, contract classes, and excluded accordion.
  - Verified visual regression suite `npx playwright test states` passing all 36 tests across all 4 viewports.
  - Rebuilt production static bundle in `app/static/`.

## Phase 5: Run Log, History, Polish
- **Deviations**: None.
- **Notes**:
  - Created `frontend/src/styles/runlog.css` implementing Section 7.10 `#pipeline-telemetry-strip.sp-runlog.sp-sheet.sp-runlog--slab` black ribbon layout, index `06`, 5 metric cells (Execution Latency, Cache Status with `.is-hit` orange fill on HIT, Ingestion & Filtering, Estimated LLM Cost, Model Engine).
  - Created `frontend/src/styles/history.css` implementing Section 7.11 `#recent-history-panel.sp-history.sp-sheet`, `.history-toggle-btn.sp-history-toggle` accordion with `07` index, count, and Expand/Collapse indicators, `#recent-history-grid.sp-history-list`, and single-ruled `.history-item-row.sp-hrow` rows with hover inversion, arrow glide, and styled verdict/status tags.
  - Wrapped `HistorySidebar` in `<div id="history-drawer">` in `App.tsx` ensuring test contract selector `#history-drawer` exists.
  - Removed obsolete `.history-item-row` and `.telemetry-strip` responsive and scroll-margin rules from `legacy.css`.
  - Added unit test suites `TelemetryDrawer.test.tsx` (5 tests) and `HistorySidebar.test.tsx` (4 tests) verifying all contract IDs, classes, ARIA attributes, toggle behaviors, cache hit styling, and selection handlers.
  - Verified visual regression suite `npx playwright test states` passing 36/36 tests across all 4 viewports.
  - Rebuilt production static bundle in `app/static/`.
