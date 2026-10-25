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
