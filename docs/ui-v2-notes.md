# Sentiment Pulse — Spec Sheet v2 Design & Architecture Notes

This document provides a comprehensive technical overview of the Spec Sheet v2 redesign completed in accordance with `docs/sentiment-pulse-spec-sheet-rebuild-plan.md`.

---

## 1. Design Overview

The "Spec Sheet" redesign represents a complete rebuild of the front-end presentation layer, replacing the legacy rounded dark-glass aesthetic with an industrial, high-density engineering spec sheet inspired by CROX and Potadot.

### Core Visual Principles
- **Light Ruled Canvas**: Off-white graph/canvas background (`#EDEDED` / `#F8F8F8`) structured with single-pixel ruled borders (`#D4D4D8` / `#18181B`).
- **Zero Border Radius**: Strict `border-radius: 0` across every element, input, button, badge, and card.
- **Zero Drop-Shadows & Backdrop-Filters**: No blur effects, no floats, and no glow filters. Depth is communicated strictly through border contrast, ruled cells, and black slab inversion.
- **Technical Slabs**: High-contrast black slab surfaces (`#0E0F10`) with stark white/off-white typography used for headers, verdict displays, run logs, and footers.
- **Precision Typography**:
  - Headings & Giant Displays: `Inter Tight` (weights 700, 800), tight tracking, sentence case displays.
  - UI Text: `Inter` (weights 400, 500, 600).
  - Data & Metrics: `JetBrains Mono` with `tabular-nums` alignment for all numerical and temporal readings.
- **Linear Hatching & Ticks**: The only permissible background patterns are repeating linear hatch lines (`repeating-linear-gradient(135deg, ...)`) and 90-degree ruler ticks (`repeating-linear-gradient(90deg, ...)`).
- **Strict Color Semantics**:
  - Canvas: `#EDEDED` (page) / `#F8F8F8` (sheet cells).
  - Ink: `#0E0F10` (primary) / `#52525B` (secondary) / `#71717A` (meta/labels).
  - Accent: `#FF5A14` (safety orange — used sparingly for active filter bars, gauge marker caps, and loading progress).
  - Buy / Positive: `#00875A` / `#D4F4E4` wash.
  - Sell / Negative / Degraded: `#C8102E` / `#FBDDE2` wash.
  - Hold: Black slab cell with hatch pattern (`--sp-hatch-on-slab`).
- **Accessibility & Contrast**: Conforms to WCAG 2.2 AA. Color is never the sole information carrier (accompanied by text words, directional symbols `▲`/`▼`/`■`, and `+`/`−` signs).

---

## 2. Design Tokens (`tokens.css`)

### Color Tokens
| Token | Value | Description |
|---|---|---|
| `--sp-canvas` | `#EDEDED` | Outer page canvas |
| `--sp-paper` | `#F8F8F8` | Primary sheet card fill |
| `--sp-cell` | `#FFFFFF` | Ruled cell background |
| `--sp-cell-hi` | `#F1F2F4` | Hover cell highlight |
| `--sp-slab` | `#0E0F10` | Black technical slab |
| `--sp-ink` | `#0E0F10` | Primary ink text / borders |
| `--sp-ink-2` | `#52525B` | Secondary text |
| `--sp-ink-3` | `#71717A` | Muted labels / metadata |
| `--sp-on-slab` | `#F3F4F6` | Primary text on black slab |
| `--sp-on-slab-2` | `#A1A1AA` | Secondary text on black slab |
| `--sp-rule` | `#D4D4D8` | Single-pixel hairline dividers |
| `--sp-rule-strong` | `#18181B` | Structural boundary borders |
| `--sp-rule-on-slab`| `#27272A` | Divider lines inside slabs |
| `--sp-orange` | `#FF5A14` | Safety orange accent |
| `--sp-buy` | `#00875A` | Buy / bullish verdict |
| `--sp-buy-wash` | `#D4F4E4` | Bullish wash tint |
| `--sp-sell` | `#C8102E` | Sell / bearish / degraded |
| `--sp-sell-wash` | `#FBDDE2` | Bearish wash tint |

### Pattern Tokens
| Token | Value |
|---|---|
| `--sp-hatch` | `repeating-linear-gradient(135deg, rgb(14 15 16 / 16%) 0 1px, transparent 1px 8px)` |
| `--sp-hatch-on-slab` | `repeating-linear-gradient(135deg, rgb(243 244 246 / 14%) 0 1px, transparent 1px 8px)` |
| `--sp-ticks` | `repeating-linear-gradient(90deg, var(--sp-ink) 0 1px, transparent 1px 8px)` |

### Typography Tokens
| Token | Value | Role |
|---|---|---|
| `--sp-font-display` | `"Inter Tight", "Inter", sans-serif` | Display headers and verdict |
| `--sp-font-ui` | `"Inter", sans-serif` | Body text and form labels |
| `--sp-font-mono` | `"JetBrains Mono", monospace` | Numbers, tickers, timestamps |
| `--sp-fs-label` | `0.6875rem` (11px) | Uppercase mono section labels |
| `--sp-fs-meta` | `0.75rem` (12px) | Footers, time, sources |
| `--sp-fs-small` | `0.8125rem` (13px) | Micro copy and notices |
| `--sp-fs-body` | `1rem` (16px) | Standard body text |
| `--sp-fs-lead` | `1.25rem` (20px) | Lead article summaries |
| `--sp-fs-section` | `clamp(2.75rem, 8vw, 7rem)` | Giant section decorative words |
| `--sp-fs-ticker` | `clamp(3.5rem, 12vw, 10rem)` | Hero ticker display |
| `--sp-fs-verdict` | `clamp(3rem, 8vw, 7rem)` | BUY / HOLD / SELL verdict word |
| `--sp-fs-counter` | `clamp(5rem, 17vw, 15rem)` | Giant loading percentage counter |
| `--sp-fs-score` | `clamp(2.25rem, 4.5vw, 4rem)` | Composite sentiment score |

---

## 3. Component Architecture Map

All presentation components reside under `frontend/src/components/` and are styled via modular CSS imports in `frontend/src/styles/index.css`.

| Section # | Component | Stylesheet | Role & Spec Features |
|---|---|---|---|
| — | `Header.tsx` | `frame.css` | Legal disclaimer strip (`#legal-disclaimer-strip`) + sticky navigation header with live ET/UTC clocks (`#session-clocks-header`). |
| — | `SectionRail.tsx` | `frame.css` | 7-step desktop rail navigation (`nav[aria-label="Page sections"]`) with intersection & mutation observation. |
| — | `LandingHero.tsx` | `landing.css` | Spec Sheet welcome card with CROX-style definition table of core pipeline concepts. |
| **01** | `SearchBar.tsx` | `input.css` | Borderless ticker input with 3px solid ink underline (`#ticker-search-input`), giant `RUN SENTIMENT` button, 6 quick chips, and toggle boxes with custom focus rings. |
| **02** | `LoadingStepper.tsx` | `loading.css` | Giant counter (`.sp-counter`), 20px progress ruler with ticks and orange fill (`.sp-ruler`), and 6-stage cell grid with active 1Hz blinking indicator. |
| **03** | `SessionWindowBanner.tsx` | `context.css` | 6-cell session spec strip (`#session-window-banner`) with green square indicator for `OPEN (RTH)` and hatch block for `CLOSED`. |
| **03** | `DecisionHero.tsx` | `signal.css` | 8/4 split slab hero (`#decision-hero-card`), giant ticker (`#result-ticker-symbol`), verdict slab (`#result-verdict-pill`) with wipe animation, 4-cell metric grid, and 28px tick gauge with hatch zone. |
| **04** | `RationaleSection.tsx` | `rationale.css` | Optional catalyst synthesis card (`#llm-synthesis-card`), single-instance synthesized pull quote, numbered inferences ledger, and observed facts list with impact badges (`▲ POSITIVE`, `▼ NEGATIVE`, `■ NEUTRAL`). |
| **05** | `EvidenceExplorer.tsx` & `EvidenceRow.tsx` | `evidence.css` | 4 filter tabs with orange bottom bar on active, ledger table with hover inversion, tri-segment FinBERT bar, expand/collapse lead drawer, and grouped excluded accordion (`#excluded-articles-list`). |
| **06** | `TelemetryDrawer.tsx` | `runlog.css` | Black ribbon run log (`#pipeline-telemetry-strip`) with 5 metric cells, orange fill highlight on cache `HIT`. |
| **07** | `HistorySidebar.tsx` | `history.css` | Collapsible history ledger (`#recent-history-panel`) inside `#history-drawer`, single-ruled rows with hover inversion and 4px arrow glide. |
| — | `SiteFooter.tsx` | `frame.css` | Static black slab footer with disclaimer and legal notice. |
| — | `App.tsx` | `frame.css`, `primitives.css` | Overall shell layout, error banner (`.sp-error`) with 10px red left bar and hatch background. |

---

## 4. Conformance & Verification Gates (Section 12)

1. **Legacy Style Deletion**:
   - `frontend/src/styles/legacy.css` was deleted completely.
   - `@fontsource/plus-jakarta-sans` was uninstalled.
   - All legacy class names (`glass-panel`, `section-card`, `btn-chip`, `badge-*`, `empty-state`, etc.) were completely eliminated.
2. **Inline Style Purity**:
   - Zero inline `style` props remain across the entire application, except for 5 strictly geometric dynamic calculations:
     - `DecisionHero.tsx`: gauge marker `left: ${markerLeftPct}%`
     - `EvidenceRow.tsx`: FinBERT tri-segment bar widths (`posPct%`, `neuPct%`, `negPct%`)
     - `LoadingStepper.tsx`: progress bar `width: ${displayPct}%`
3. **Automated Conformance Suite (`conformance.spec.ts`)**:
   - Body luminance > 0.8 confirmed on all pages.
   - Elements with `border-top-left-radius > 0` count: **0**.
   - Elements with `backdrop-filter ≠ none` count: **0**.
   - Elements with `box-shadow ≠ none` count: **0**.
   - Background images containing unauthorized gradients count: **0**.
   - Zero horizontal overflow at 320px, 375px, 768px, 1024px, and 1440px.
   - Section rail visibility: visible at 1440px, hidden at 1024px.
   - Hero `h2` font size ≥ 96px at 1440px.
4. **Visual Regression Harness (`states.spec.ts`)**:
   - Produced 36 full-page screenshots across all 9 required states at 4 viewports (1440x900, 1024x768, 768x1024, 375x812) saved to `frontend/tests/visual/__out__/after/`.
5. **Backend & Test Integrity**:
   - 66 frontend unit tests passing across 13 test suites.
   - 286 backend unit, contract, and integration tests passing (`pytest -q`).
   - Zero modifications to business logic, API endpoints, or database contracts.
