# Sentiment Pulse — Front-End Rebuild Plan ("Spec Sheet" v2)

**For:** the execution agent (Gemini). **Repo:** `elem160/Market-Sentiment-2`. **Scope:** `frontend/` only (plus rebuilt `app/static/`).
**Supersedes:** `docs/sentiment-pulse-minimal-ui-overhaul-plan.md`. Do not follow that file. Where the two disagree, this one wins.

---

## 0. Read this first

### 0.1 What went wrong last time

The first redesign (PR #1, `redesign/minimal-ui`) came out as the same page in new colours. The cause was in the old plan, not in the execution. It told the agent to:

- keep every existing CSS class name ("Do not rename them");
- keep the existing DOM order and component order;
- forbid a side navigation;
- keep telemetry and history exactly where they were;
- restyle "in place" with "no JSX/state changes in Phase 1".

An agent that obeys those rules can only recolour. This plan removes those restrictions on purpose.

### 0.2 What this job is

A **rebuild of the presentation layer**. New layout, new page structure, new type, new components, new CSS. Business logic does not change.

The result must look like it was designed by a different person, on a different day, for a different product. Put the old screenshot (dark blue, rounded glass cards, cyan accents) next to the new one: nothing should look related.

### 0.3 How to work

1. Work **one phase at a time** (Section 11). Finish it, run the checks, commit, then **stop and report**. Do not start the next phase until told to.
2. Do not "improve" the design on your own. If this plan is silent, pick the option closest to the references in Section 2 and note the choice in `docs/ui-v2-deviations.md`.
3. Never shrink a requirement because it is hard. If you cannot do something, write it in the deviations file and say so in your report.
4. When this plan gives a CSS value, use it. Do not substitute "similar" values.

---

## 1. Rules

### 1.1 FROZEN — business logic (do not touch)

Same list as before, and it still holds:

- Everything outside `frontend/` except the rebuilt `app/static/**`. No edits to `app/**` (Python), `alembic/**`, `tests/**` (Python), `scripts/**`.
- `frontend/src/services/api.ts`, `frontend/src/api/*`, `frontend/src/types.ts`, `frontend/src/utils/formatters.ts`, `frontend/src/utils/time.ts`.
- In `App.tsx`: `handleSearch`, `handleSelectHistoricalRun`, every `useState`/`useRef`/`useEffect`, the SSE logic, stale-request logic, props passed into child components, and every conditional that decides **what** renders.
- Verdict thresholds, `getCompositeColor` thresholds (`> 0.25`, `< -0.25`), `isCorroborated`, `isEvidenceFreeHold`, `formatScore`, `formatHoldReason`, filter logic and counts, excluded-article grouping, history fetch/refresh, clock intervals, default toggle values (`forceRefresh=false`, `enableLlm=true`), `maxLength={16}`, input uppercasing, disabled rules.
- Every value shown today must still be shown. You may change **how** and **where**, never **whether**.

### 1.2 TEST CONTRACT — the only names you must keep

Existing tests and `tests/visual/visual.spec.ts` depend on these. Everything not listed here may be renamed, moved or deleted.

**IDs** (keep on an element of the same kind, inside the same logical section):
`#root`, `#legal-disclaimer-strip`, `#header-clock-et`, `#header-clock-utc`, `#search-section`, `#ticker-search-input`, `#run-analysis-btn`, `#force-refresh-checkbox`, `#enable-llm-checkbox`, `#quick-chip-<slug>` (generated, six of them), `#analysis-stepper`, `#session-window-banner`, `#decision-hero-card`, `#result-ticker-symbol`, `#result-verdict-pill`, `#result-composite-score`, `#result-confidence-score`, `#rationale-section`, `#llm-synthesis-card`, `#rationale-grid`, `#synthesized-rationale-text`, `#evidence-explorer`, `#excluded-articles-list`, `#pipeline-telemetry-strip`, `#recent-history-panel`, `#recent-history-grid`.

**Classes** (only these five):
`form.search-form`, `.history-item-row`, `.history-toggle-btn`, `.filter-tab`, `.filter-tab.active`.

**ARIA pairs:** `aria-controls="excluded-articles-list"` + `aria-expanded`; `aria-controls="recent-history-grid"` + `aria-expanded`; filter buttons keep `role="tab"` + `aria-selected`; `role="alert"` on errors; `role="status"` on the progress message.

**Text the tests look up** (each must exist in exactly one element where `getByText` is used):

| Text | Rule |
|---|---|
| `Recent Analysis Queries` | One element, in the history toggle. |
| ticker label (`$MSFT`, `$AAPL`, `EUR/USD`, `GC=F`) | `#result-ticker-symbol` contains **only** the label text. Never render the ticker twice as visible text (no outline duplicate, no ghost copy). The history row renders its own label once. |
| `Validating ticker symbol …` | The progress message renders in exactly one element. |
| rationale `summary` string | Renders once. Do not repeat it as a pull-quote plus a body paragraph. |
| `Corroborated`, `Uncorroborated`, `Single Publisher`, `Insufficient Corroboration`, `N Supporting Source(s)` | Keep the exact strings from `DecisionHero.tsx`. Do not add any other element containing "corroborated". A section label reading "Corroboration" is fine. |

Run `npm test` after every phase. **Never edit an existing assertion to make it pass.** A failing existing test means you broke the contract.

### 1.3 FREE — everything else

You may, and in most cases must:

- rewrite the JSX structure inside every component;
- change the DOM order of sections inside `App.tsx` **as long as each section's render condition is untouched**;
- add new presentational components and presentational hooks (see 7.x);
- add local presentation-only `useState` (e.g. an article row's open/closed state);
- delete and rename any CSS class outside 1.2;
- delete `styles/index.css` and replace it with several smaller files;
- add a side navigation (Section 7.2);
- add fonts (`@fontsource/inter-tight`);
- shorten the input placeholder (it cannot fit at display size). Keep the helper text below it unchanged.

### 1.4 Legal and trust — must stay visible

- `#legal-disclaimer-strip` stays at the very top of the page, always visible, never collapsed, never truncated at any width. Text unchanged.
- The `heuristic-footnote` content in `DecisionHero` (the `result.disclaimer` string plus the "14-hour half-life… uncalibrated empirical defaults" sentence) stays visible without interaction, directly under the metrics.
- All warnings (NO FRESH NEWS, NO RELEVANT NEWS, DEGRADED INGESTION) keep their exact copy and roles.
- BUY/HOLD/SELL is always a written word plus an icon. Colour never carries the verdict alone.

### 1.5 Git — nothing touches `main`

`main` already contains PR #1. Branch from it.

```powershell
git switch main
git pull origin main
git switch -c redesign/spec-sheet-v2
git push -u origin redesign/spec-sheet-v2
```

- Each phase: `git switch redesign/spec-sheet-v2` then `git switch -c redesign/spec-sheet-v2-pN-<slug>`.
- Commits use Conventional Commits, imperative, narrow: `feat(ui): add section rail`, `refactor(ui): rebuild decision hero`, `test(ui): add design conformance spec`.
- Push the phase branch and open a PR **into `redesign/spec-sheet-v2`**. The owner reviews and merges by hand.
- The final PR (`redesign/spec-sheet-v2` → `main`) is opened only when the owner says so, and merged only by the owner.
- Forbidden: committing to `main`, pushing to `main`, merging into `main`, `git push --force`, `git reset --hard` on shared branches. Rollback is `git revert`.
- Never commit `.env`, `data/`, `*.db`.

### 1.6 Banned (instant fail in review)

- Any dark-blue canvas, navy, cyan, teal, or purple accent.
- Any `border-radius` above `0` (exception: the native checkbox box can stay square too; use 0 everywhere).
- Any `backdrop-filter`, blur, glass/translucent card, drop shadow, glow, or `linear-gradient`/`radial-gradient` used as decoration. The only allowed gradients are the **hatch** and **tick** patterns defined in Section 3.
- Amber/yellow/gold anywhere. Caution states use ink + hatch (Section 3.4).
- Class names or markup carried over from the old UI: `glass-panel`, `section-card`, `hero-decision-card`, `metrics-strip`, `metric-item`, `article-card`, `stepper-card`, `stages-grid`, `stage-node`, `telemetry-strip`, `telemetry-cell`, `badge-buy/-hold/-sell/-neutral`, `btn-chip`, `empty-state`. After Phase 6 a search for these must return **zero** hits in `frontend/src` (tests excluded).
- New npm runtime dependencies other than `@fontsource/inter-tight`. No animation library, no chart library, no CSS framework, no component library.
- Fake data. Every number on screen comes from the existing result object or is a static fact already stated in the code (Section 7.3 lists the allowed ones).

---

## 2. Design direction

### 2.1 What I took from the two reference sites

I read both sites on 25 Oct 2026. These are the traits to translate. Copy the **ideas**, not the content, logos, copy or assets.

**CROX (`crox.framer.website`) — the skeleton and the voice**

| Observed | Use in Sentiment Pulse |
|---|---|
| Light grey canvas, white cells, solid black cells, one hot orange accent | Same colour budget (Section 3). |
| Sharp corners everywhere. Content sits in a **visible grid of ruled cells** | Every section is a "sheet": 1 px ruled cells, zero radius. |
| Huge all-caps tight grotesk headings: `WORK`, `PROCESS`, `ABOUT`, `404` | Giant section words (`SIGNAL`, `RATIONALE`, `EVIDENCE`) and a giant ticker. |
| Tiny mono/caps labels over big values; a "System status" spec table (`Repeatability ±0.008 mm`, `Field recalls 0`) | Metric cells and context strip use label-over-value spec cells. Landing hero has a spec table. |
| Index lists: number, name, category, year, arrow | Evidence becomes a ledger of rows with index numbers. |
| Black ribbon with big stat cells at the bottom of sections; orange stat tile | Run log is a black ribbon; the active/primary cell is orange. |
| Diagonal-hatch boxes; ruler tick marks (`IIIIIIII`) | Hatch = HOLD and caution. Ticks = gauges and progress. |
| Hover on a row inverts it to black | Evidence rows and history rows invert on hover. |

**Potadot (`potadot.com.my`) — the structure and the flow**

| Observed | Use in Sentiment Pulse |
|---|---|
| Boot loader: a big `000%` counter with a caption | The loading state is a giant `037%` counter driven by the **real** progress value. |
| Numbered nav `01 Home … 07 Contact`; step counters `01 / 04` | A numbered section rail `01 Input … 07 History`; stage counters `03 / 06`. |
| Each section: small eyebrow, big H2, one-line intro | Same header pattern on every section. |
| Emphasised words inside headlines (*Excel*, *one system*) | One word per headline in the accent colour. |
| Product-UI mini-panels (stock balance, dashboard tiles) showing how it works | Metric cells with real gauges and segment meters built from the real values. |
| Numbered "why us" list, numbered process steps | Rationale inferences become a numbered ledger. |
| Calm cool-grey surface, generous spacing | Canvas `#E6E8EB`, 16–24 px gaps between sheets. |

### 2.2 The concept: "Spec Sheet"

The page reads like a printed engineering spec for one asset. A grid of ruled cells. Large type for the three things that matter (ticker, verdict, score). Small mono type for everything auditable. One orange accent for action and position. Black slabs for emphasis.

### 2.3 Old vs new at a glance

| | Old (and PR #1) | New |
|---|---|---|
| Theme | Dark | **Light** canvas with black slabs |
| Shapes | Rounded cards, glass | **Sharp**, 1 px ruled cells |
| Page | One centred column | **Left section rail** + wide sheet column |
| Type | Small UI type, caps labels | **Giant** display type + mono labels |
| Input | Boxed search bar | **Oversized** underlined input, 6-cell chip strip |
| Loading | Six small cards | **Giant live % counter** + tick ruler + numbered stage row |
| Signal | Card with pill and four mini cards | **Split slab**: giant ticker left, inverted verdict slab right, gauge cells below |
| Rationale | Two cards | **Pull statement + numbered ledger** and a **facts table** |
| Evidence | Stack of cards | **Index ledger** with inline expand |
| Telemetry | Strip of cells | **Black ribbon** |
| History | Glass panel and grid | **Ledger list** |
| Palette | Cyan, green, amber, red | Ink, orange, green, red. **No amber.** |

---

## 3. Design tokens

Create `frontend/src/styles/tokens.css` with exactly this.

```css
:root {
  color-scheme: light;

  /* Surfaces */
  --sp-canvas: #E6E8EB;      /* page */
  --sp-cell: #F3F4F6;        /* default cell */
  --sp-cell-hi: #FFFFFF;     /* raised / hovered cell */
  --sp-slab: #0E0F10;        /* black slab */
  --sp-slab-2: #1B1D1F;      /* cell inside a slab */

  /* Ink */
  --sp-ink: #0E0F10;
  --sp-ink-2: #34373C;
  --sp-ink-3: #585D64;       /* min colour for small text on cells (6.0:1) */
  --sp-on-slab: #F3F4F6;
  --sp-on-slab-2: #B9BEC5;

  /* Rules */
  --sp-rule: #C2C6CC;        /* hairline between cells */
  --sp-rule-strong: #0E0F10; /* outer frame, section tops */

  /* Accent: action, focus, position. Never a status. */
  --sp-accent: #FF5A14;
  --sp-accent-deep: #B83700; /* accent as text on light (5.3:1) */
  --sp-on-accent: #0E0F10;   /* text on accent fill (6.2:1) */

  /* Status. Always paired with a word, sign or icon. */
  --sp-buy: #0A7D43;
  --sp-buy-wash: #DCF2E4;
  --sp-sell: #C8102E;
  --sp-sell-wash: #FBDDE2;

  /* Patterns (the only allowed gradients) */
  --sp-hatch: repeating-linear-gradient(135deg, rgb(14 15 16 / 16%) 0 1px, transparent 1px 8px);
  --sp-hatch-on-slab: repeating-linear-gradient(135deg, rgb(243 244 246 / 14%) 0 1px, transparent 1px 8px);
  --sp-ticks: repeating-linear-gradient(90deg, var(--sp-ink) 0 1px, transparent 1px 8px);

  /* Type */
  --sp-font-display: "Inter Tight", "Inter", ui-sans-serif, system-ui, sans-serif;
  --sp-font-ui: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --sp-font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace;

  --sp-fs-label: 0.6875rem;   /* 11px mono labels, uppercase, 0.08em */
  --sp-fs-meta: 0.75rem;      /* 12px */
  --sp-fs-small: 0.8125rem;   /* 13px */
  --sp-fs-body: 1rem;
  --sp-fs-lead: 1.25rem;
  --sp-fs-h3: clamp(1.5rem, 2.4vw, 2rem);
  --sp-fs-section: clamp(2.75rem, 8vw, 7rem);     /* SIGNAL / EVIDENCE words */
  --sp-fs-ticker: clamp(3.5rem, 12vw, 10rem);
  --sp-fs-ticker-long: clamp(2.25rem, 7vw, 5.5rem); /* tickers over 8 chars */
  --sp-fs-verdict: clamp(3rem, 8vw, 7rem);
  --sp-fs-counter: clamp(5rem, 17vw, 15rem);
  --sp-fs-score: clamp(2.25rem, 4.5vw, 4rem);

  --sp-track-label: 0.08em;
  --sp-track-display: -0.045em;

  /* Space (4px base) */
  --sp-1: 0.25rem; --sp-2: 0.5rem; --sp-3: 0.75rem; --sp-4: 1rem;
  --sp-5: 1.25rem; --sp-6: 1.5rem; --sp-8: 2rem; --sp-10: 2.5rem;
  --sp-12: 3rem; --sp-16: 4rem;
  --sp-sheet-gap: clamp(0.75rem, 1.6vw, 1.5rem);
  --sp-cell-pad: clamp(0.875rem, 1.6vw, 1.5rem);

  /* Layout */
  --sp-rail-w: 13.5rem;
  --sp-page-max: 112rem;
  --sp-nav-h: 3.5rem;

  /* Motion */
  --sp-ease: cubic-bezier(0.2, 0.8, 0.2, 1);
  --sp-t-fast: 120ms;
  --sp-t-base: 200ms;
  --sp-t-enter: 420ms;
}
```

### 3.1 Colour rules

- Orange is for: the primary button, the active rail item, section index squares, the "emphasis word" in headlines, the progress fill, one highlighted run-log cell. It never means BUY/SELL/HOLD or good/bad.
- Orange fills always carry `--sp-on-accent` (ink) text and a 1 px ink border. Orange is never used for small text on a light cell; use `--sp-accent-deep`.
- Green and red appear only on verdict, sign, score, impact and meters. Always next to a word, `+`/`−` sign, or icon.
- **HOLD is neutral:** ink slab plus hatch. That is how orange stays unambiguous.

### 3.2 Base styles (`styles/base.css`)

- `html { background: var(--sp-canvas); scroll-behavior: smooth; }` (smooth off under reduced motion).
- `body { margin:0; font: 400 var(--sp-fs-body)/1.5 var(--sp-font-ui); color: var(--sp-ink); }`
- `*, *::before, *::after { box-sizing: border-box; border-radius: 0; }`
- `h1,h2,h3,h4,p { margin:0 }`, `button { font: inherit; border-radius: 0 }`.
- `.sp-mono { font-family: var(--sp-font-mono); font-variant-numeric: tabular-nums; }`
- `.sp-label { font: 500 var(--sp-fs-label)/1.2 var(--sp-font-mono); letter-spacing: var(--sp-track-label); text-transform: uppercase; color: var(--sp-ink-3); }`
- `.sp-display { font-family: var(--sp-font-display); font-weight: 800; letter-spacing: var(--sp-track-display); line-height: 0.88; text-transform: uppercase; }`
- Selection: `::selection { background: var(--sp-accent); color: var(--sp-ink); }`

### 3.3 Primitives (`styles/primitives.css`)

Build these once, reuse everywhere.

```css
/* A sheet = a ruled grid of cells. */
.sp-sheet {
  display: grid;
  gap: 1px;
  background: var(--sp-rule);                /* the gap shows this colour = hairlines */
  border: 1px solid var(--sp-rule-strong);
  border-top-width: 3px;                     /* heavy top rule, CROX-style */
}
.sp-sheet > * { background: var(--sp-cell); min-width: 0; }
.sp-cell { padding: var(--sp-cell-pad); display: flex; flex-direction: column; gap: var(--sp-2); }
.sp-cell--slab { background: var(--sp-slab) !important; color: var(--sp-on-slab); }
.sp-cell--hatch { background-image: var(--sp-hatch); }
.sp-cell--slab.sp-cell--hatch { background-image: var(--sp-hatch-on-slab); }

/* Tag = bordered mono box. */
.sp-tag { display:inline-flex; align-items:center; gap:.375rem; padding:.2rem .5rem;
  border:1px solid currentColor; font: 500 var(--sp-fs-label)/1.1 var(--sp-font-mono);
  letter-spacing: var(--sp-track-label); text-transform: uppercase; }
.sp-tag--solid { background: var(--sp-ink); color: var(--sp-on-slab); border-color: var(--sp-ink); }
.sp-tag--buy { color: var(--sp-buy); background: var(--sp-buy-wash); }
.sp-tag--sell { color: var(--sp-sell); background: var(--sp-sell-wash); }
.sp-tag--hatch { background-image: var(--sp-hatch); }

/* Section header. Same on every section. */
.sp-sec-head { display:grid; grid-template-columns: auto 1fr auto; align-items:end; gap: var(--sp-4); }
.sp-sec-index { width:2.5rem; height:2.5rem; display:grid; place-items:center;
  background: var(--sp-accent); color: var(--sp-on-accent); border:1px solid var(--sp-ink);
  font: 600 var(--sp-fs-small)/1 var(--sp-font-mono); }
.sp-sec-word { font-size: var(--sp-fs-section); }           /* with .sp-display */
.sp-sec-word em { font-style: normal; color: var(--sp-accent-deep); }  /* emphasis word */

/* Buttons */
.sp-btn { display:inline-flex; align-items:center; justify-content:center; gap:.5rem; min-height:3rem;
  padding:0 1.25rem; border:1px solid var(--sp-ink); background: var(--sp-accent); color: var(--sp-on-accent);
  font: 600 var(--sp-fs-small)/1 var(--sp-font-mono); letter-spacing: var(--sp-track-label); text-transform: uppercase;
  cursor:pointer; transition: background var(--sp-t-fast) var(--sp-ease), color var(--sp-t-fast) var(--sp-ease); }
.sp-btn:hover:not(:disabled) { background: var(--sp-ink); color: var(--sp-on-slab); }
.sp-btn:disabled { background: var(--sp-cell); color: var(--sp-ink-3); border-color: var(--sp-rule); cursor:not-allowed; }
.sp-btn--ghost { background: transparent; color: var(--sp-ink); }

/* Focus */
:focus-visible { outline: 3px solid var(--sp-ink); outline-offset: 2px; box-shadow: 0 0 0 5px var(--sp-accent); }
.sp-on-slab :focus-visible, .sp-cell--slab :focus-visible { outline-color: var(--sp-on-slab); }
```

### 3.4 Hatch means "caution or neutral-hold"

Caution banners: ink 1 px border, hatch background, `!` icon, bold ink text. No yellow. DEGRADED uses the same layout with a `--sp-sell` 6 px left bar.

### 3.5 Fonts

```powershell
cd frontend
npm install @fontsource/inter-tight
```

In `main.tsx`, keep the Inter and JetBrains Mono imports and add:

```ts
import '@fontsource/inter-tight/600.css';
import '@fontsource/inter-tight/700.css';
import '@fontsource/inter-tight/800.css';
```

`@fontsource/plus-jakarta-sans` is already unused in `main.tsx`; remove it from `package.json` with `npm uninstall @fontsource/plus-jakarta-sans` at the end of Phase 6. Never load fonts from a CDN.

---

## 4. Page architecture

### 4.1 Frame (≥ 1200 px)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ■ RESEARCH ONLY  Not investment advice or solicitation. Directional …  (black)│  #legal-disclaimer-strip
├──────────────────────────────────────────────────────────────────────────────┤
│ SENTIMENT PULSE   REAL-TIME MARKET SENTIMENT INTELLIGENCE  │ ET 13:28:25 │ UTC 17:28:25 │  sticky nav, 56px
├────────────┬─────────────────────────────────────────────────────────────────┤
│ 01 Input   │  [ landing hero — only when there is no result/loading/error ]  │
│ 02 Context │  ┌ 01 ── INPUT ───────────────────────────────────────────────┐ │
│ 03 Signal  │  │ NVDA_                                    [RUN SENTIMENT →] │ │
│ 04 Ration. │  │ chips  ▢ $NVDA ▢ $AAPL ▢ EUR/USD ▢ USD/JPY ▢ GC=F ▢ BTC-USD │ │
│ 05 Evid.   │  │ run options  ▢ Force fresh run   ▢ Nemotron 3 catalyst     │ │
│ 06 Run log │  └────────────────────────────────────────────────────────────┘ │
│ 07 History │  [ loading counter  OR  result sheets ]                         │
│ (sticky)   │                                                                 │
└────────────┴─────────────────────────────────────────────────────────────────┘
```

- `.sp-page`: `display:grid; grid-template-columns: var(--sp-rail-w) minmax(0,1fr); max-width: var(--sp-page-max); margin: 0 auto; gap: var(--sp-sheet-gap); padding: var(--sp-sheet-gap);`
- Rail: `position: sticky; top: calc(var(--sp-nav-h) + var(--sp-sheet-gap)); align-self: start;`
- Main: sheets stacked with `gap: var(--sp-sheet-gap)`.
- Each section element gets `scroll-margin-top: calc(var(--sp-nav-h) + 1rem)`.

### 4.2 Below 1200 px

Rail disappears. Page is one column. Sheet column fills the width with `padding: var(--sp-4)`.

### 4.3 Section order in the DOM and on screen

Keep the existing order and conditions. Only the landing hero moves to the top.

1. `LandingHero` (new; renders under the **same condition** the empty state used: `!analysisResult && !isLoading && !errorMessage`)
2. `SearchBar`
3. error block (same condition)
4. `LoadingStepper` (same condition)
5. result: `SessionWindowBanner`, `DecisionHero`, `RationaleSection`, `EvidenceExplorer`, `TelemetryDrawer` (same condition)
6. `HistorySidebar`
7. `SiteFooter` (new, static)

### 4.4 Section header pattern

Every major sheet starts with `.sp-sec-head`: orange index square (`01`–`07`), a mono label, and a mono meta label on the right. Signal, Rationale and Evidence also carry a giant word via `.sp-display.sp-sec-word` with one emphasised word in `<em>`.

---

## 5. Motion (CSS only)

Allowed, all disabled under `prefers-reduced-motion: reduce`:

| Where | Effect | Timing |
|---|---|---|
| Sheets on first render | `opacity 0→1`, `translateY(10px→0)`; stagger children by 40 ms with `animation-delay` via `:nth-child` | `--sp-t-enter` |
| Verdict slab | `clip-path: inset(0 100% 0 0)` → `inset(0)` wipe | 480 ms |
| Evidence/history row hover | background → ink, text → on-slab (invert) | `--sp-t-fast` |
| Button / chip hover | fill swap orange ↔ ink | `--sp-t-fast` |
| Progress fill | `width` transition | `--sp-t-base` |
| Active loading stage | 1 Hz blinking square (`steps(2)`) | only while loading |
| Gauge marker | `left` transition | `--sp-t-base` |

No parallax, no scroll-jacking, no marquee, no cursor effects, no JS animation, no counting-up numbers (the loading counter shows the real value as it arrives).

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
  .sp-verdict { clip-path: none !important; }
}
```

---

## 6. File layout for the new CSS

Delete `frontend/src/styles/index.css` in Phase 6 (see 11). Until then it is renamed `legacy.css` (see Phase 1). New files:

```text
frontend/src/styles/
  index.css        # only @imports, in this order
  tokens.css
  base.css
  primitives.css
  frame.css        # .sp-page, nav, rail, footer, legal strip
  landing.css
  input.css
  loading.css
  context.css
  signal.css
  rationale.css
  evidence.css
  runlog.css
  history.css
  motion.css
  responsive.css   # all @media queries that change layout
```

`main.tsx` keeps `import './styles/index.css'`. Each component imports nothing; CSS is global through `index.css`. Keep each file under about 250 lines.

---

## 7. Components

Naming: all new classes are prefixed `sp-`. Component files keep their current names so imports in `App.tsx` do not change, except the new ones.

### 7.1 `Header.tsx` — legal strip + sticky nav

Keep the clock `useEffect`, intervals and formatting exactly. Replace the JSX.

```text
<div id="legal-disclaimer-strip" class="sp-legal" role="region" aria-label="Research Disclaimer">
  <span class="sp-tag sp-tag--accent">Research only</span>        ← new short tag; static text
  <span><strong>RESEARCH & SENTIMENT EXPERIMENT ONLY:</strong> …exact existing sentence…</span>
</div>
<header class="sp-nav">
  <div class="sp-nav-brand">
    <h1 class="sp-display sp-nav-title">Sentiment Pulse</h1>
    <span class="sp-label sp-nav-sub">Real-Time Market Sentiment Intelligence</span>
  </div>
  <div class="sp-nav-clocks" role="group" aria-label="Session clocks">
    <div class="sp-clock" title="Eastern Time (NYSE/NASDAQ Market Anchor)">
      <span class="sp-label">ET</span><span id="header-clock-et" class="sp-mono" aria-label="Eastern Time: {timeEt}">{timeEt}</span>
    </div>
    <div class="sp-clock" title="Coordinated Universal Time">
      <span class="sp-label">UTC</span><span id="header-clock-utc" class="sp-mono" aria-label="UTC: {timeUtc}">{timeUtc}</span>
    </div>
  </div>
</header>
```

CSS:
- `.sp-legal`: black slab, full-bleed, `padding: .625rem var(--sp-cell-pad)`, mono 12 px, `display:flex; gap:.75rem; align-items:flex-start`. Wraps on mobile. Never `text-overflow`.
- `.sp-nav`: `position: sticky; top: 0; z-index: 20; height: var(--sp-nav-h); background: var(--sp-cell); border-bottom: 1px solid var(--sp-rule-strong); display:flex; justify-content:space-between;` no blur, no shadow.
- `.sp-nav-title`: 1.5rem, 800. `.sp-nav-sub` hidden below 900 px.
- `.sp-clock`: bordered cell, `padding: 0 var(--sp-4)`, left rule `1px`, label above value (label 11 px, value 14 px mono). Clocks must not be `aria-live`.
- Remove the brand icon tile, the pulse dot and the Activity icon.

### 7.2 `SectionRail.tsx` — NEW, presentational

A numbered index, like Potadot's nav. It has no effect on app state.

```tsx
const ITEMS = [
  { n: '01', id: 'search-section',           label: 'Input'     },
  { n: '02', id: 'session-window-banner',    label: 'Context'   },
  { n: '03', id: 'decision-hero-card',       label: 'Signal'    },
  { n: '04', id: 'rationale-section',        label: 'Rationale' },
  { n: '05', id: 'evidence-explorer',        label: 'Evidence'  },
  { n: '06', id: 'pipeline-telemetry-strip', label: 'Run log'   },
  { n: '07', id: 'recent-history-panel',     label: 'History'   },
] as const;
```

Behaviour:
- Renders `<nav class="sp-rail" aria-label="Page sections"><ol>…</ol></nav>`. Each item is `<a href="#id">` with the number in mono and the label in display caps.
- **Presence:** an item is a link only if `document.getElementById(id)` exists; otherwise render a `<span aria-disabled="true">` in `--sp-ink-3`. Recompute with a `MutationObserver` on `document.querySelector('main')` (`childList: true, subtree: true`), debounced with `requestAnimationFrame`. Call `setState` only when the joined id string actually changed (avoids render loops).
- **Active item:** `IntersectionObserver` with `rootMargin: '-40% 0px -55% 0px'`. The active item gets orange background, ink text, `aria-current="location"`.
- **jsdom safety (critical):** the existing `App.test.tsx` renders `<App/>` in jsdom, which has no `IntersectionObserver`. Guard: `if (typeof IntersectionObserver === 'undefined') return;`. Do the same for `MutationObserver`. If this is missed, existing tests crash.
- Hidden below 1200 px (`display:none` in `responsive.css`).
- Rail style: one sheet, rows separated by hairlines, 56 px per row, hover inverts to ink.

Place in `App.tsx`:

```tsx
<div className="sp-page">
  <SectionRail />
  <main className="sp-main"> …unchanged conditionals… </main>
</div>
```

`<Header/>` stays above `.sp-page`. Keep `className="app-container"` off; use `sp-app`.

### 7.3 `LandingHero.tsx` — NEW (replaces the old empty state)

Render under the exact old condition, keep `role="region" aria-label="Welcome and usage introduction"`. Keep the old copy.

```text
<section class="sp-landing sp-sheet" role="region" aria-label="Welcome and usage introduction">
  <div class="sp-cell sp-landing-title">
    <span class="sp-label">Session-anchored news sentiment</span>
    <h2 class="sp-display">Live Market <em>Sentiment</em> <span class="sp-amp">&amp;</span> Catalyst Intelligence</h2>
  </div>
  <div class="sp-cell sp-landing-copy">
    <p>Enter any US equity, ETF, forex pair (e.g. EUR/USD), commodity future (e.g. GC=F), or crypto asset to execute session-anchored news ingestion, FinBERT neural scoring, and corroboration synthesis.</p>
  </div>
  <dl class="sp-cell sp-spec">   ← spec table (CROX "System status")
    <div><dt>Scoring model</dt><dd>FinBERT</dd></div>
    <div><dt>Recency half-life</dt><dd>14 h</dd></div>
    <div><dt>Corroboration gate</dt><dd>≥ 2 publishers</dd></div>
    <div><dt>Result cache</dt><dd>15 min</dd></div>
    <div><dt>Instruments</dt><dd>Equity · ETF · FX · Futures · Crypto</dd></div>
  </dl>
</section>
```

Allowed static facts (all already stated in the code today): FinBERT, 14-hour half-life, ≥ 2 supporting publishers, 15-minute cache, the five instrument types. Do **not** add any other number.

CSS: title cell spans 8 columns on ≥ 1024 px, spec table spans 4; `h2` uses `--sp-fs-section`, 3–4 lines, `em` in `--sp-accent-deep`, `&` in `--sp-accent` (decorative, `aria-hidden` not needed). `.sp-spec` rows: `dt` mono label left, `dd` mono value right, hairline between rows, one row highlighted with an orange left bar.

### 7.4 `SearchBar.tsx` — "01 Input"

Keep all state, handlers, chip data, generated chip ids, titles, disabled logic. Replace markup and classes.

```text
<section id="search-section" class="sp-input sp-sheet" aria-label="Asset analysis input">
  <div class="sp-cell sp-sec-head"> [01] <span class="sp-label">Input</span> <span class="sp-label">Run an analysis</span> </div>

  <div class="sp-cell sp-input-main">
    <label for="ticker-search-input" class="sp-label">Asset symbol</label>
    <form class="search-form sp-input-form" onSubmit=…>
      <input id="ticker-search-input" class="sp-input-field" … aria-describedby="ticker-format-helper" placeholder="ENTER TICKER" />
      <button id="run-analysis-btn" class="sp-btn sp-btn--xl" …> …same two states, text unchanged… → </button>
    </form>
    <span id="ticker-format-helper" class="sp-helper">…exact helper text…</span>
  </div>

  <div class="sp-chip-strip" role="group" aria-label="Multi-asset quick chips">
    <span class="sp-label sp-chip-label">Quick chips</span>
    {chips → <button id="quick-chip-…" class="sp-chip" …>{chip.label}</button>}
  </div>

  <div class="sp-options" role="group" aria-label="Run options">
    <span class="sp-label">Run options</span>
    <label class="sp-toggle" title="…"> <input id="force-refresh-checkbox" type="checkbox" …/> <span class="sp-toggle-box" aria-hidden="true"></span> <RefreshCw/> <span>Force Fresh Run</span> </label>
    <label class="sp-toggle" title="…"> <input id="enable-llm-checkbox" … /> … <span>Nemotron 3 Catalyst Filter</span> </label>
  </div>
</section>
```

CSS:
- `.sp-input-field`: no box. `font: 800 clamp(2.25rem, 7vw, 5.5rem)/1 var(--sp-font-display)`; uppercase; `letter-spacing: var(--sp-track-display)`; `border: 0; border-bottom: 3px solid var(--sp-ink); background: transparent; width:100%; padding: .25rem 0; caret-color: var(--sp-accent);` placeholder colour `--sp-rule`.
- `.sp-input-form`: `display:grid; grid-template-columns: minmax(0,1fr) auto; gap: var(--sp-6); align-items:end`.
- `.sp-btn--xl`: `min-height: 4.5rem; padding: 0 2rem; font-size: 1rem`.
- Chips: `grid-template-columns: auto repeat(6, 1fr)` on desktop; each chip is a cell with mono text, min-height 3.5rem, invert on hover. Below 900 px: 3 columns, then 2.
- Toggles: native checkbox visually hidden (not `display:none`), custom 20 px square box with a ✓ drawn by CSS when `:checked`; `:focus-visible` on the input shows the focus ring on the box (`input:focus-visible + .sp-toggle-box`). Checked state = filled ink box + ✓, so it is not colour-only. Min target 44 px.
- Disabled (loading): reduce to `--sp-ink-3` text, no hover.

### 7.5 `LoadingStepper.tsx` — giant counter

Keep `STAGES`, keys, `currentIdx`, `displayPct`, the `role="progressbar"` attributes, `#analysis-stepper`, the live status message, and the `RUNNING PIPELINE FOR {ticker}` text.

```text
<section id="analysis-stepper" class="sp-loading sp-sheet sp-cell--slab-wrap" aria-label="Analysis pipeline progress">
  <div class="sp-cell sp-cell--slab sp-loading-top">
    <span class="sp-label">Running pipeline for {formatTickerLabel(ticker)}</span>   ← keep existing uppercase text
    <div class="sp-counter sp-display" aria-hidden="true">{String(displayPct).padStart(3,'0')}<span>%</span></div>
    <div class="sp-ruler" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={displayPct} aria-label="Pipeline execution progress">
      <div class="sp-ruler-fill" style={{ width: `${Math.max(5, displayPct)}%` }} />
    </div>
    <div class="sp-loading-msg sp-mono" role="status" aria-live="polite"> &gt; {message} </div>
  </div>
  <ol class="sp-stages" aria-label="Pipeline stages">
    {STAGES.map → <li class="sp-stage is-done|is-active|is-queued" aria-label="{label}: {statusLabel}">
        <span class="sp-label">{String(idx+1).padStart(2,'0')} / 06</span>
        <span class="sp-stage-name">{label without the "1. " prefix?}</span>   ← keep STAGES labels untouched; render s.label as-is
        <span class="sp-tag">{DONE | RUNNING | QUEUED}</span>
      </li>}
  </ol>
</section>
```

The counter is `aria-hidden` because the progressbar and the status message already announce progress. The percent is the real `displayPct`, never animated by JS.

CSS:
- `.sp-counter`: `font-size: var(--sp-fs-counter); line-height:.8; color: var(--sp-on-slab)`; the `%` in `--sp-accent`.
- `.sp-ruler`: height 20 px; background `var(--sp-ticks)` inverted for slab (use `repeating-linear-gradient(90deg, var(--sp-on-slab-2) 0 1px, transparent 1px 8px)`); `.sp-ruler-fill` is orange, height 100%, `mix-blend-mode: normal`, `transition: width var(--sp-t-base)`.
- `.sp-stages`: 6 equal cells on ≥ 1024 px, 3×2 on 640–1023, 1 column below. Active cell: orange fill with ink text. Done cell: ink text with a ✓ prefix. Queued cell: `--sp-ink-3`.
- Active stage tag gets the blinking square (`::before`, `steps(2)`).
- Remove spinners entirely. Use the blinking square.

### 7.6 `SessionWindowBanner.tsx` — "02 Context"

Keep: `session` fallback, `formatSessionName`, `isMarketOpen`, `formatEt`/`formatUtc` calls, the `title` tooltips, and the `null` return.

Render as a six-cell spec strip:

```text
<aside id="session-window-banner" class="sp-context sp-sheet" aria-label="Market session and news temporal window">
  <div class="sp-cell"><span class="sp-label">Session</span><strong class="sp-display sp-ctx-big">{formatSessionName(...)}</strong></div>
  <div class="sp-cell"><span class="sp-label">Market status</span>
     <strong class="sp-ctx-status {open|closed}"><Dot/> {icon}<span>OPEN (RTH)</span> | <span>CLOSED</span></strong></div>
  <div class="sp-cell" title="Active news filter boundary in Eastern Time"><span class="sp-label">Window · ET</span><span class="sp-mono">{formatEt(start)} → {formatEt(end)}</span></div>
  <div class="sp-cell" title="…UTC"><span class="sp-label">Window · UTC</span><span class="sp-mono">…</span></div>
  <div class="sp-cell"><span class="sp-label">Lookback</span><span class="sp-mono sp-ctx-num">{(session.window_duration_hours || 0).toFixed(1)}h</span></div>
  <div class="sp-cell" title="Pipeline execution timestamp"><span class="sp-label">Run</span><span class="sp-mono">{formatUtc(session.run_timestamp_utc)}</span></div>
</aside>
```

- Open: solid green square + word `OPEN (RTH)`. Closed: hollow ink square + word `CLOSED` on a hatch background. No amber.
- The text "lookback" must remain visible (label + value). Value text can drop the word "lookback" because the label holds it.
- Grid: `grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr))`.

### 7.7 `DecisionHero.tsx` — "03 Signal" (the main event)

Keep every expression: `verdict`, `verdictClass`, `getVerdictIcon` (icons may be larger), `formatScore`, `formatHoldReason`, `distinctPubs`, `supportingPubs`, `isCorroborated`, `isEvidenceFreeHold`, every conditional, every string. Replace `getCompositeColor`'s inline `style` with a class chosen by the **same thresholds**:

```ts
const compositeTone = (s: number) => (s > 0.25 ? 'is-pos' : s < -0.25 ? 'is-neg' : 'is-flat');
```

Structure:

```text
<section id="decision-hero-card" class="sp-signal {buy|hold|sell}" aria-label="Directional market sentiment classification">

  <div class="sp-sec-head sp-signal-head"> [03] <span class="sp-label">Signal</span> <span class="sp-label">Current algorithmic classification</span> </div>

  <div class="sp-signal-main sp-sheet">                    ← 12-col grid: 8 / 4 on desktop
    <div class="sp-cell sp-signal-id">
      <div class="sp-tags"> asset_type tag · [Cached Result] · [No Fresh News] · [No Relevant News] · [Degraded]  ← same conditions & text </div>
      <h2 id="result-ticker-symbol" class="sp-display sp-ticker" data-len={label.length > 8 ? 'long' : 'short'}>{formatTickerLabel(result.ticker, result.asset_type)}</h2>
      <div class="sp-company">{result.company_name}</div>
    </div>

    <div class="sp-cell sp-cell--slab sp-verdict {verdictClass}">
      <span class="sp-label">Classification</span>
      <div id="result-verdict-pill" class="sp-verdict-word sp-display"> {getVerdictIcon()} <span>{verdict}</span> </div>
      {verdict === 'HOLD' && result.hold_reason && <div class="sp-hold-reason sp-mono">Reason: {formatHoldReason(result.hold_reason)}</div>}
    </div>
  </div>

  {…the three data_status banners, same conditions/roles/copy… as <div class="sp-notice [sp-notice--degraded]" role="status|alert"> icon + <strong>…</strong> text </div>}

  <div class="sp-metrics sp-sheet" role="group" aria-label="Supporting metrics">
    <div class="sp-cell sp-metric sp-metric--wide">          ← Composite Sentiment (span 2 cols)
      <span class="sp-label">Composite Sentiment</span>
      <div id="result-composite-score" class="sp-score sp-mono {compositeTone}">{formatScore(result.sentiment_score)}</div>
      <div class="sp-gauge" aria-hidden="true">
        <div class="sp-gauge-zone" />                         ← neutral band −0.25…+0.25 (hatch)
        <div class="sp-gauge-marker" style={{ left: `${Math.min(100, Math.max(0, ((result.sentiment_score + 1) / 2) * 100))}%` }} />
      </div>
      <div class="sp-gauge-scale sp-mono" aria-hidden="true"><span>−1.00</span><span>0</span><span>+1.00</span></div>
      <div class="sp-metric-sub">Range [-1.00 to +1.00]</div>
    </div>

    <div class="sp-cell sp-metric">                          ← Confidence Level
      <span class="sp-label">Confidence Level</span>
      <div id="result-confidence-score" class="sp-score-sm sp-mono">{…same expression…}</div>
      {!isEvidenceFreeHold && <div class="sp-seg" aria-hidden="true">{10 spans, first Math.round(conf*10) have .on}</div>}
      <div class="sp-metric-sub">{…same nested ternary…}</div>
    </div>

    <div class="sp-cell sp-metric">                          ← Evidence Quality
      <span class="sp-label">Evidence Quality</span>
      <div class="sp-score-sm sp-mono">{…}%</div>
      <div class="sp-seg" aria-hidden="true">…</div>
      <div class="sp-metric-sub">{…} Retained Articles</div>
    </div>

    <div class="sp-cell sp-metric">                          ← Publisher Corroboration
      <span class="sp-label">Publisher Corroboration</span>
      {isCorroborated ? <span class="sp-tag sp-tag--buy"><CheckCircle2/> Corroborated</span> : <span class="sp-tag sp-tag--hatch"><AlertTriangle/> {…same three-way text…}</span>}
      <div class="sp-metric-sub">{…same Supporting/Distinct Source(s) text…}</div>
    </div>
  </div>

  <div class="sp-footnote sp-cell--slab" role="note" aria-label="Research disclaimer">
    <span class="sp-tag sp-tag--accent">Research use only</span>      ← new static tag; must not contain the word "corroborated"
    <span><strong>{result.disclaimer || 'Research & Market Sentiment Tool. Not Financial or Investment Advice.'}</strong> Decision formulation uses exponential recency decay (14-hour half-life) with strict corroboration gating. All thresholds are uncalibrated empirical defaults.</span>
  </div>
</section>
```

CSS highlights:
- `.sp-ticker`: `font-size: var(--sp-fs-ticker)`; `[data-len="long"]` uses `--sp-fs-ticker-long`; `overflow-wrap: anywhere`; `line-height:.82`. This stops `BTC-USD`, `EUR/USD`, 16-char tickers from overflowing.
- `.sp-verdict` backgrounds (slab base):
  - `.buy`: background `--sp-buy`, text white (contrast 5.2:1).
  - `.sell`: background `--sp-sell`, text white (5.9:1).
  - `.hold`: background `--sp-slab` + hatch-on-slab, text on-slab.
- `.sp-verdict-word`: `font-size: var(--sp-fs-verdict)`; icon 1em, stroke 2.5; `clip-path` wipe animation.
- `.sp-score`: `font-size: var(--sp-fs-score)`, weight 500; `.is-pos` → `--sp-buy`, `.is-neg` → `--sp-sell`, `.is-flat` → `--sp-ink`. The sign is part of the text, so colour is redundant.
- `.sp-gauge`: height 28 px, `background: var(--sp-ticks)`, 1 px ink border; zone is the centre 25% of the width with hatch; marker is a 14×36 ink rectangle, `translateX(-50%)`, orange 3 px top cap.
- `.sp-seg`: 10 spans, 100% wide, `gap: 2px`, each 10 px tall; `.on` fills `--sp-ink`; off = `--sp-rule`.
- `.sp-metrics`: `grid-template-columns: 2fr 1fr 1fr 1fr` (≥ 1200), `1fr 1fr` (640–1199) with the wide cell spanning both, `1fr` below 640.
- `.sp-notice`: hatch background, 1 px ink border, 6 px left bar (ink, or `--sp-sell` for DEGRADED), icon + text.
- `.sp-footnote`: black slab, mono 12 px, orange tag. Must be fully visible at 320 px.
- Do not render `result.ticker` anywhere else in this component.

### 7.8 `RationaleSection.tsx` — "04 Rationale"

Keep: `facts`, `inferences`, `summary`, `articlesMap`, `getImpactBadgeClass` logic (rename the returned class names to your own), the `llmSummary` condition, `modelVersions?.llm`, `formatUtc`.

```text
<section id="rationale-section" class="sp-rationale" aria-label="Analysis method and rationale">
  <div class="sp-sec-head"> [04] label  | giant word: <h3 class="sp-display sp-sec-word">Why <em>this</em> call</h3> | meta </div>

  {llmSummary && <div id="llm-synthesis-card" class="sp-sheet sp-llm"><div class="sp-cell sp-cell--slab">
      <div class="sp-llm-head"><span class="sp-label">Catalyst synthesis</span>{modelVersions?.llm && <span class="sp-tag">Model: {modelVersions.llm}</span>}</div>
      <p class="sp-llm-body">{llmSummary}</p></div></div>}

  <div id="rationale-grid" class="sp-sheet sp-rationale-grid">             ← 5 / 7 columns on desktop
    <div class="sp-cell sp-rationale-left">
      <span class="sp-label">Synthesized directional rationale</span>
      <div id="synthesized-rationale-text">
        <p class="sp-pull">{summary}</p>                                   ← rendered ONCE
        {inferences.length > 0 && <ol class="sp-ledger">{inferences.map((inf,i) =>
           <li><span class="sp-mono sp-ledger-n">{String(i+1).padStart(2,'0')}</span><span>{inf}</span></li>)}</ol>}
      </div>
      <span class="sp-label sp-formula">Formula &amp; sentiment drivers</span>
    </div>

    <div class="sp-cell sp-rationale-right">
      <div class="sp-facts-head"><span class="sp-label">Observed &amp; reported facts</span><span class="sp-tag">{facts.length} Statements</span></div>
      {facts.length === 0 ? <p class="sp-empty">No verified catalyst statements extracted for this session window.</p>
       : <ul class="sp-facts" aria-label="Observed catalyst statements">{facts.map → <li>
            <span class="sp-mono sp-fact-n">{idx}</span>
            <div><p>{fact.statement}</p>
              <div class="sp-fact-meta sp-mono">{cited publisher} · {date UTC} · {category} · <span class="sp-impact is-pos|is-neg|is-flat">{impact}</span></div></div></li>}</ul>}
    </div>
  </div>
</section>
```

CSS:
- `.sp-pull`: Inter Tight 700, `clamp(1.5rem, 2.6vw, 2.5rem)`, line-height 1.1, tracking −0.02em, sentence case (not uppercase).
- `.sp-ledger li`: grid `3rem 1fr`, hairline between rows, number in `--sp-accent-deep`.
- `.sp-facts li`: grid `2.5rem 1fr`, hairline between rows.
- `.sp-impact`: mono caps; pos → buy colour with `▲` prefix, neg → sell with `▼`, flat → ink-3 with `■`. Word is always present.
- The inline `style=` props in the old file all go away. Zero inline styles in this component.

### 7.9 `EvidenceExplorer.tsx` + `EvidenceRow.tsx` — "05 Evidence"

Keep all logic: `filter`, `showExcluded`, `threshold`, partitions, counts, filtered list, `excludedByReason`, `totalExcludedCount`, `excludedCountsMap`, `art.lead_text.slice(0, 500)`, URL link attributes, weights fallback.

New file `components/EvidenceRow.tsx` (presentational). It takes `art`, `index`, `showSentiment` and owns one `useState<boolean>` for expand/collapse.

Evidence sheet:

```text
<section id="evidence-explorer" class="sp-evidence" aria-label="Evidence explorer">
  <div class="sp-sec-head"> [05] <span class="sp-label">Evidence</span> … <h3 class="sp-display sp-sec-word">Evi<em>dence</em></h3>
       <p class="sp-label">Session News Evidence ({retainedArticles.length} Retained)</p> </div>

  <div class="sp-filter" role="tablist" aria-label="Sentiment filters">
     4 × <button role="tab" aria-selected class="filter-tab sp-filter-tab {active}">All (n) | Bullish (n) | Bearish (n) | Neutral (n)</button>
  </div>

  <div class="sp-ledger-table" role="region" aria-label="Filtered articles">
     <div class="sp-ledger-head sp-label" aria-hidden="true"> # · Headline · Source · Time · Sentiment · Weight </div>
     {filteredArticles.map((art, i) => <EvidenceRow key={art.article_id} … />)}
  </div>

  …excluded block…
</section>
```

`filter-tab` is the test contract class; keep `active` on the selected one. Filter bar styling: 4 equal cells, selected = ink fill with on-slab text and a 4 px orange bottom bar; others invert on hover. Counts stay in the label text.

Empty filtered state keeps its exact sentence, inside a 160 px min-height hatch cell.

`EvidenceRow` markup:

```text
<article class="sp-row" data-open={open}>
  <div class="sp-row-main">
     <span class="sp-mono sp-row-n">{String(index+1).padStart(2,'0')}</span>
     <div class="sp-row-title">
        {art.canonical_url ? <a href=… target="_blank" rel="noopener noreferrer" class="sp-row-link"><span>{art.title}</span><ExternalLink size={14} aria-hidden="true"/></a>
                           : <span class="sp-row-link">{art.title}</span>}
     </div>
     <div class="sp-row-src"><strong>{art.canonical_publisher || art.source_name}</strong><span class="sp-mono">{art.provider}</span></div>
     <div class="sp-row-time sp-mono"><span>{art.published_at_utc ? `${formatUtc(art.published_at_utc)} UTC` : 'Undated'}</span>{art.age_hours != null && <span>age: {art.age_hours.toFixed(1)}h</span>}</div>
     <div class="sp-row-sent" aria-label="FinBERT scores: positive {…} percent, neutral {…} percent, negative {…} percent">
        <span class="sp-mono sp-row-score is-pos|is-neg|is-flat">{signed finbert_directional_score, 2 decimals}</span>
        <span class="sp-tri" aria-hidden="true"><i style="width:pos%" class="p"/><i style="width:neu%" class="u"/><i style="width:neg%" class="n"/></span>
     </div>
     <div class="sp-row-w sp-mono">{Eff. Weight: x.xxx | Weight: x.xxx | —}</div>
     <button type="button" class="sp-row-toggle" aria-expanded={open} aria-controls="row-{id}-detail" onClick=…>{open ? 'Less −' : 'Details +'}</button>
  </div>
  {open && <div id="row-{id}-detail" class="sp-row-detail">
     {art.lead_text && <p>{art.lead_text.slice(0, 500)}</p>}
     <div class="sp-mono sp-row-pct">+{pos}% pos · {neu}% neu · −{neg}% neg</div></div>}
</article>
```

- Use the same defaults as the old code for missing FinBERT values: `pos = finbert_positive ?? 0.1`, `neg ?? 0.1`, `neu ?? 0.8`.
- Row grid on ≥ 1100 px: `3rem minmax(0,2.2fr) minmax(0,1.1fr) 9.5rem 9rem 8rem auto`. Between 640–1099: two lines (n + title + toggle, then a 3-column meta grid). Below 640: stacked, 44 px toggle.
- `.sp-tri`: 8 px tall, three segments side by side; `.p` buy colour, `.u` rule colour with hatch, `.n` sell colour. The words are in the aria-label and in the detail line, so it is never colour-only.
- Hover/focus-within: row inverts (ink background, on-slab text, link underlined). Keep link colour readable on the inverted background.
- Long headlines wrap (`overflow-wrap:anywhere`). No ellipsis on headlines.
- No row ever animates its height.

Excluded block: keep the button (`.btn-link` becomes `.sp-excl-toggle`), `aria-expanded`, `aria-controls="excluded-articles-list"`, the label `Excluded from scoring ({totalExcludedCount} total)`, `#excluded-articles-list`, reasons grouped with `(Showing X of Y)`. Style: hatch background sheet, group header = hatch tag with the reason, rows = `EvidenceRow`-lite (no sentiment/weight columns, same as the old excluded card content). Remove all inline styles.

### 7.10 `TelemetryDrawer.tsx` — "06 Run log"

Keep all five cells and every expression. Render as a black ribbon.

```text
<section id="pipeline-telemetry-strip" class="sp-runlog sp-sheet sp-runlog--slab" aria-label="Technical run telemetry">
  <div class="sp-cell sp-cell--slab sp-runlog-title"><span class="sp-sec-index">06</span><span class="sp-label">Run log</span></div>
  5 × <div class="sp-cell sp-cell--slab"><span class="sp-label"><Icon/> Execution Latency</span><span class="sp-mono sp-runlog-val">…</span></div>
</section>
```

- Values in mono 1.25–1.75 rem on-slab; labels `--sp-on-slab-2`.
- The **Cache Status** cell is the orange cell when `cache_status === 'HIT'` (orange fill, ink text); otherwise a normal slab cell. Same condition as the old inline colour.
- Grid: 6 columns ≥ 1200, 3 columns 640–1199, 1 column below.

### 7.11 `HistorySidebar.tsx` — "07 History"

Keep: `history` state, fetch effect, `isOpen`, `getVerdictBadge` logic, `formatTimeWithTz`, the `history.length === 0` early return, `onSelectRun`, `aria-label` on each row.

```text
<section id="recent-history-panel" class="sp-history sp-sheet" aria-label="Recent analysis history">
  <button type="button" class="history-toggle-btn sp-history-toggle" aria-expanded={isOpen} aria-controls="recent-history-grid" onClick=…>
     <span class="sp-sec-index">07</span>
     <span class="sp-history-title">Recent Analysis Queries ({history.length})</span>
     <span class="sp-mono">{isOpen ? 'Collapse −' : 'Expand +'}</span>
  </button>
  {isOpen && <div id="recent-history-grid" class="sp-history-list">
     {history.map(item => <button type="button" class="history-item-row sp-hrow" aria-label="View analysis for {item.ticker}" onClick=…>
        <span class="sp-hrow-ticker sp-display">{formatTickerLabel(item.ticker, item.asset_type)}</span>
        <span class="sp-tag sp-tag--buy|sell|hatch">{verdict}</span>
        {asset type tag, status tags — same conditions/text}
        <span class="sp-mono sp-hrow-time">{formatTimeWithTz(item.run_timestamp_utc)}</span>
        <ArrowRight aria-hidden="true"/> </button>)}</div>}
</section>
```

- `getByText('$MSFT')` must find one element: the ticker lives only in `.sp-hrow-ticker`.
- Row: one line on desktop (`grid-template-columns: 12rem auto 1fr auto 2rem`), hairline between rows, 56 px min height, hover inverts, arrow slides 4 px right on hover (disabled under reduced motion).
- HOLD tag = hatch + ink border. BUY = green wash. SELL = red wash. Word always shown.
- Remove all inline styles and the `glass-panel` class.

### 7.12 `App.tsx` — frame and error

- Only JSX shape and classNames change. Keep all hooks, handlers and conditions.
- Error block: `<div class="sp-error" role="alert">` with a 10 px `--sp-sell` left bar, mono `ERR` tag, `AlertCircle` icon, `<strong>Analysis Error:</strong> {errorMessage}`. Hatch background. Remove the inline `style`.
- Remove the old empty-state block and render `<LandingHero/>` under the same condition, above `<SearchBar/>`.
- Add `<SiteFooter/>` (new, static): black slab, mono 12 px: `SENTIMENT PULSE · SESSION-ANCHORED NEWS SENTIMENT · RESEARCH USE ONLY`. Do not copy any string the tests query.

---

## 8. Responsive spec

| Width | Behaviour |
|---|---|
| ≥ 1200 | Rail + main. Signal 8/4 split. Metrics 2:1:1:1. Evidence 7-column rows. Run log 6 cells in a row. |
| 1024–1199 | No rail. Signal 8/4. Metrics 2×2 with wide cell spanning the first row. Evidence rows in two lines. |
| 768–1023 | Signal stacks: ticker cell, then verdict slab full width. Context 3×2. Stages 3×2. Chips 3 columns. |
| 640–767 | As above; nav subtitle hidden; clocks stay. |
| < 640 | One column everywhere. Input and button stack (button full width, 56 px). Chips 2 columns. Metrics 1 column. Context 1 column. Evidence rows stacked. Run log 1 column. Legal strip wraps to as many lines as needed. |
| 320 | No horizontal page scroll. Ticker uses the `long` size if over 8 characters. Verdict never clipped. |

All layout-changing media queries live in `responsive.css`. Use `min-width` queries going up where practical.

---

## 9. Accessibility

Target WCAG 2.2 AA.

1. Contrast: every pair in Section 3 meets 4.5:1 for small text and 3:1 for large text and UI. Do not introduce new greys. Never use `--sp-ink-3` on a slab, and never use orange for small text on light.
2. Focus: the global `:focus-visible` rule in 3.3. Sticky nav must not cover a focused element (`scroll-margin-top` on sections and on focusable rows).
3. Targets: 44×44 px minimum for chips, toggles, row toggles, filter tabs, history rows.
4. Colour is never the only signal: verdict word, `+`/`−` sign, impact word + symbol, tag words, OPEN/CLOSED word, gauge numbers.
5. Decorative visuals (`.sp-gauge`, `.sp-seg`, `.sp-tri`, `.sp-ruler`, `.sp-counter`) are `aria-hidden`; the same information is available as text.
6. Live regions: only the progress message (`role="status"`) and errors (`role="alert"`). Clocks are not live.
7. DOM order equals reading order at every width. Do not use CSS `order`.
8. Headings: one `h1` (nav brand). `h2` for Landing, ticker, and section titles; `h3` for the giant section words. No skipped levels inside a section.
9. The rail is a real `<nav>` with an `<ol>`; disabled items are not focusable.

---

## 10. What to leave alone

- Python code, API, SSE, schemas, generated types.
- Test files: you may **add** tests; do not weaken existing ones.
- `frontend/src/utils/*`, `frontend/src/services/*`, `frontend/src/api/*`, `frontend/src/types.ts`.

---

## 11. Phases

Each phase ends with: run the checks (Section 12.1), commit, push the phase branch, open a PR into `redesign/spec-sheet-v2`, then **stop and report**. Include `app/static` rebuilt by `npm run build` in each phase commit (CI at the end requires it to match).

### Phase 0 — Baseline and screenshot harness
Branch `redesign/spec-sheet-v2-p0-harness`. Commit `test(ui): add mocked visual harness`.

1. Create the integration branch (1.5).
2. `cd frontend; npm ci` and record that `typecheck`, `lint`, `test`, `build` pass.
3. Add `frontend/tests/visual/fixtures.ts`: typed `AnalysisResult` objects for: BUY (corroborated, 12+ articles incl. one without URL and one undated), HOLD/NO_FRESH_NEWS, SELL/DEGRADED, a result with `llm_summary`, and a result with excluded articles in two reasons. Build them from `src/types.ts` and the mock in `App.test.tsx`.
4. Add `frontend/tests/visual/states.spec.ts`. It uses `page.route('**/api/v1/**', …)` to mock: health, the analyze POST (return **200** with the fixture so the cached path renders immediately), and the history endpoint (check `getHistory` in `services/api.ts` for the exact URL). It also mocks a job flow for the loading state (202 + a progress stream, or hold the analyze request open to show the stepper). It saves full-page PNGs to `frontend/tests/visual/__out__/<phase>/<state>-<width>.png` at 1440×900, 1024×768, 768×1024, 375×812. States: empty, loading (≈ 37 %), BUY, HOLD no-news, SELL degraded, evidence filtered to empty, excluded expanded, history expanded, error.
5. Add `__out__/` to `.gitignore`.
6. Run it on the current UI and save the output as `__out__/before/`. This is the "before" set.

**Done when:** the harness runs with `npx playwright test states` without a backend; before-screenshots exist; existing checks pass.

### Phase 1 — Foundations and frame
Branch `…-p1-foundations`. Commit `feat(ui): add spec-sheet tokens, frame and section rail`.

1. Install `@fontsource/inter-tight`; add the imports (3.5).
2. Rename `styles/index.css` → `styles/legacy.css`. In it, delete the whole `:root` block, every `body`/`html` rule, and every rule on `.app-container`, `.main-content`, `.app-header`, `.disclaimer-strip` (these are replaced). Add a short **compat block** at the top of `legacy.css` mapping the old variable names the unmigrated components still use (`--color-ink`, `--color-ink-soft`, `--color-ink-muted`, `--color-line`, `--color-accent`, `--color-positive`, `--color-negative`, `--color-caution`, `--color-surface`, `--font-display`, `--font-data`, etc.) to the new light tokens, so unmigrated components stay legible. Mark the file `/* TEMPORARY: deleted in Phase 6 */`.
3. Create `tokens.css`, `base.css`, `primitives.css`, `frame.css`, `landing.css`, `motion.css`, `responsive.css` and a new `index.css` that imports `tokens, base, primitives, frame, landing, …, legacy` in that order.
4. Rebuild `Header.tsx` (7.1), add `SectionRail.tsx` (7.2), add `LandingHero.tsx` (7.3), add `SiteFooter.tsx`, update `App.tsx` frame and error block (7.12).
5. Add tests: `SectionRail.test.tsx` (renders 7 items; does not crash without `IntersectionObserver`), `LandingHero.test.tsx` (renders the exact paragraph and the spec rows).

**Done when:** checks pass; the page has a light canvas, black legal strip, sticky nav, rail, landing hero; the rest may still look hybrid (legacy components on a light canvas) — that is expected until later phases.

### Phase 2 — Input, loading, context
Branch `…-p2-input-loading`. Commit `feat(ui): rebuild input, loading counter and context strip`.

Implement 7.4, 7.5, 7.6 with `input.css`, `loading.css`, `context.css`. Delete the matching rules from `legacy.css`.

**Done when:** every chip submits its value; both toggles work with the keyboard; the form submits on Enter; the giant counter shows the real percentage; `form.search-form` and all IDs exist; tests pass.

### Phase 3 — Signal
Branch `…-p3-signal`. Commit `feat(ui): rebuild decision hero as split signal slab`.

Implement 7.7 with `signal.css`. Update `DecisionHero.test.tsx` **only by adding** cases: `data-len` is `long` for a 12-character ticker; the gauge marker `left` for scores −1, 0, +1 is 0 %, 50 %, 100 %; a `.is-pos/.is-neg/.is-flat` tone at 0.26, −0.26 and 0.25. Do not touch existing assertions.

**Done when:** BUY, HOLD (every hold reason), SELL, cached, no-fresh, no-relevant, degraded all render with the exact old copy; disclaimer visible; existing tests unchanged and green.

### Phase 4 — Rationale and evidence
Branch `…-p4-rationale-evidence`. Commit `feat(ui): rebuild rationale ledger and evidence table`.

Implement 7.8, 7.9 (`EvidenceRow.tsx`) with `rationale.css`, `evidence.css`. Add tests: row expand/collapse toggles `aria-expanded` and shows `lead_text`; filter counts unchanged; excluded block expands and keeps `aria-controls`.

**Done when:** counts per filter and excluded grouping match the fixtures; every article is reachable by keyboard; no inline `style=` remains in these two components except the computed `width`/`left` values.

### Phase 5 — Run log, history, polish
Branch `…-p5-runlog-history`. Commit `feat(ui): rebuild run log and history ledger`.

Implement 7.10, 7.11 with `runlog.css`, `history.css`. Finish `motion.css` (Section 5): staggered entrances, verdict wipe, hover inversions, reduced-motion block.

**Done when:** history toggle, row click and refresh behave as before; `.history-toggle-btn`, `.history-item-row` exist; reduced-motion verified.

### Phase 6 — Delete legacy, harden, final gates
Branch `…-p6-harden`. Commit `chore(ui): remove legacy styles and run conformance gates`.

1. Delete `legacy.css` and its import. Fix anything that breaks.
2. `npm uninstall @fontsource/plus-jakarta-sans`.
3. Run the banned-name search (12.2). Result must be empty.
4. Add `tests/visual/conformance.spec.ts` (12.3) and make it pass.
5. Responsive and keyboard pass at 320, 375, 768, 1024, 1440, plus 200 % zoom.
6. Produce the **after** screenshots in `__out__/after/`, then run the grayscale difference check (12.4).
7. Write `docs/ui-v2-notes.md`: design decisions, token list, component map, any deviations.
8. Final `npm ci && npm run gen:api && git diff --exit-code src/api/schema.d.ts && npm run typecheck && npm run lint && npm test && npm run build && git diff --exit-code ../app/static` (run `git add ../app/static` before the last diff or commit the build first).

**Done when:** all of Section 12 passes. Do **not** open the PR to `main`. Report to the owner.

---

## 12. Verification

### 12.1 Commands (PowerShell, from `frontend/`)

```powershell
npm ci
npm run gen:api
git diff --exit-code src/api/schema.d.ts
npm run typecheck
npm run lint
npm test
npm run build
cd ..
git diff --check
git status --short
```

Backend suite is read-only confidence (`pytest -q` from repo root). It must be unaffected.

### 12.2 "Not a reskin" — structural gate

These must hold at the end of Phase 6.

```powershell
# 1. Old names gone (tests excluded). Expected: no output.
Select-String -Path frontend\src\**\*.tsx,frontend\src\styles\*.css -Pattern 'glass-panel|section-card|hero-decision-card|metrics-strip|metric-item|article-card|stepper-card|stages-grid|stage-node|telemetry-strip|telemetry-cell|badge-(buy|hold|sell|neutral)|btn-chip|empty-state' -Exclude *.test.tsx

# 2. No inline styles except computed geometry. Review every hit.
Select-String -Path frontend\src\components\*.tsx -Pattern 'style=\{\{' -Exclude *.test.tsx

# 3. Old stylesheet is gone.
Test-Path frontend\src\styles\legacy.css   # False
```

Also: `git diff --stat main...HEAD -- frontend/src/components` must show every component file modified, and `frontend/src/styles` must contain only the files listed in Section 6.

### 12.3 Design conformance spec (`tests/visual/conformance.spec.ts`)

With the mocked harness, at 1440 and 375, on the empty state and on the BUY result:

- `body` computed background luminance > 0.8 (light theme).
- Count of elements with computed `border-top-left-radius` > 0 is **0**.
- Count of elements with `backdrop-filter` ≠ `none` is **0**.
- Count of elements with `box-shadow` ≠ `none` is 0 when nothing is focused.
- No element has a computed `background-image` containing `linear-gradient` or `radial-gradient` except those that use the hatch or tick patterns (match `repeating-linear-gradient`).
- `document.documentElement.scrollWidth <= window.innerWidth` (no horizontal scroll) at 320, 375, 768.
- `#legal-disclaimer-strip` is visible and its text is not clipped (`scrollWidth <= clientWidth`).
- At 1440: `nav[aria-label="Page sections"]` is visible; at 1024 it is not.
- The `h2` inside `#decision-hero-card` has computed `font-size` ≥ 96 px at 1440 for `$NVDA`.
- `#result-ticker-symbol` text equals the label exactly.

### 12.4 Visual difference check

Convert `before/` and `after/` 1440×900 screenshots to grayscale, resize both to 720 px wide, and compute the mean absolute pixel difference. A recolour of the old layout scores low (the luminance structure is the same). Require **> 25 %** mean difference on the empty state and on the BUY result. This is a soft gate; the owner's eyes are the real one.

```python
from PIL import Image, ImageChops
import numpy as np, sys
a = Image.open(sys.argv[1]).convert("L").resize((720, 450))
b = Image.open(sys.argv[2]).convert("L").resize((720, 450))
print(round(np.asarray(ImageChops.difference(a, b)).mean() / 255 * 100, 1), "% mean difference")
```

### 12.5 Functional parity checklist

- [ ] Health check runs once on mount; failure is silent.
- [ ] Ticker input uppercases, keeps `maxLength=16`; Enter submits; blank or loading disables submit.
- [ ] Each quick chip sets the ticker and starts a run with the current toggle values.
- [ ] Force Fresh Run defaults off; Nemotron 3 Catalyst Filter defaults on; both pass through unchanged.
- [ ] Loading shows the same stage, percent and message; error shows the same message.
- [ ] Choosing a history item loads that run and cancels any active one.
- [ ] Every field of `AnalysisResult` that showed before still shows (session, hero, rationale, evidence, telemetry, history).
- [ ] All BUY/HOLD/SELL and HOLD-reason strings, corroboration states and data-status banners match the old text exactly.
- [ ] Filter counts, filtered results, excluded grouping and `(Showing X of Y)` match the fixtures.
- [ ] External links keep `target="_blank"` and `rel="noopener noreferrer"`.
- [ ] Section 1.2 IDs, classes, ARIA pairs and test text all present.

### 12.6 Screenshot matrix (review set)

`after/` at 1440×900, 1024×768, 768×1024, 375×812: empty, loading, BUY, HOLD no-news, SELL degraded, filter-empty, excluded expanded, history expanded, error.

---

## 13. Risks

| Risk | Control |
|---|---|
| `IntersectionObserver`/`MutationObserver` missing in jsdom breaks existing tests | Feature-guard both (7.2). Add a test. |
| Duplicate text breaks `getByText` | Section 1.2 rules: ticker once, summary once, progress message once, no extra "corroborated" text. |
| Giant type overflows on long tickers | `data-len` switch + `overflow-wrap:anywhere`. Test at 16 characters on a 320 px viewport. |
| Hybrid look in Phases 1–4 confuses review | Expected. The compat block in `legacy.css` keeps unmigrated parts legible; judge each phase only on what it migrated. |
| Static bundle drift fails CI at the final PR | Run `npm run build` and commit `app/static` in every phase; re-check in Phase 6. |
| Agent drifts back to rounded dark cards | Banned list (1.6) and the conformance spec (12.3) fail the build of the phase. |
| Loading counter feels fake | It displays the real `displayPct` only. No timers, no easing in JS. |

Rollback: `git revert <commit>` on the phase branch, PR as usual. Never reset or force-push.

---

## 14. Handoff prompt (paste above this document when you start the agent)

> You are executing `sentiment-pulse-spec-sheet-rebuild-plan.md` in the repo `elem160/Market-Sentiment-2`. This is a full rebuild of the front-end presentation layer, not a reskin. The previous attempt failed because it kept the old layout and class names; this plan deliberately removes those limits. Business logic, API calls, state management and data shapes must not change. Follow Section 1 exactly: respect the test contract in 1.2, obey the banned list in 1.6, and never commit or push to `main`. Work one phase at a time starting with Phase 0. After each phase run the Section 12.1 commands, commit on the phase branch, push, then stop and report what changed, what you verified, and any deviations (also recorded in `docs/ui-v2-deviations.md`). Do not begin the next phase until I say so.
