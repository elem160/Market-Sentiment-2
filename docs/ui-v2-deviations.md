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
