# Sentiment Pulse — Minimal UI/UX Overhaul Implementation Plan

**Status:** implementation-ready plan only; no product code has been changed.  
**Authoring date:** 25 October 2026.  
**Scope:** visual design, layout, accessibility, and interaction polish for the existing frontend only.

## 0. Executive decision

Redesign Sentiment Pulse as a calm, editorial *decision workspace*, not a neon “terminal” dashboard. The screen should answer, in this order: **what was analysed, what the model’s current directional classification is, how trustworthy the evidence is, and why**. Everything else is available in the same page but has less visual weight.

The selected direction is a warm near-black canvas, off-white typography, one restrained cobalt information accent, and semantic green/amber/red reserved solely for data meaning. Borders replace glass, gradients, and ambient glows. Large, purposeful typography and a rigid 12-column grid provide the minimal, art-directed quality requested while preserving the density and auditability a market-sentiment tool needs.

### Non-negotiable constraints

The following requirements are copied verbatim for the execution agent:

- UI/UX ONLY. Do not change functionality: no changes to business logic, API calls, data flow, state management, scoring/decision logic, endpoints, data shapes, element IDs or hooks the logic depends on, or feature behavior. Every existing feature must remain present and working. Only presentation, layout, styling, and interaction polish may change.
- The research/not-financial-advice disclaimers must stay clearly visible. You may restyle them, not remove or hide them.
- NEVER commit or push to main. All work happens on dedicated branches (for example one integration branch such as `redesign/minimal-ui`, with small feature branches per phase merged into it). The plan must define the branch names, commit conventions, push steps, and how I review and merge manually. Nothing merges to main without my approval.

## 1. Research record and assumptions

### 1.1 Reference-site analysis: ZEGGO

The corrected [Awwwards ZEGGO entry](https://www.awwwards.com/sites/zeggo) and the linked [ZEGGO live site](https://www.zeggo.com.sg/) were reviewed on 25 October 2026. Awwwards identifies the work as Minimal, Typography, 3D, Interaction Design, Microinteractions, GSAP, Three.js, and Astro. Those are observations about the reference—not technologies to import into Sentiment Pulse.

#### What makes the reference work

| Dimension | Observed ZEGGO treatment | What is worth translating |
|---|---|---|
| Layout and grid | The live site uses a full-viewport black canvas, very large areas of empty space, asymmetrical anchoring, a slim persistent navigation row, and sequential numbered sections. | Give the application a strong macro-layout: a quiet masthead, generous section boundaries, a dominant signal area, and numbered/eyebrow-level orientation only where it helps scanning. Keep the application’s content grid structured and dense enough for financial evidence. |
| Typography | Extremely large all-caps wordmark/display moments are paired with small, clean sans-serif navigation and restrained copy. Scale, rather than many card treatments, establishes hierarchy. | Let ticker and key score/verdict own the display scale; use a clear, quiet UI scale everywhere else. Do not reproduce ZEGGO’s logo typography or turn ordinary dashboard labels into display type. |
| Palette | Nearly pure black canvas, white type, grey structural lines, and one vivid orange brand accent create a very limited colour budget. | Use an almost-black canvas, warm white ink, muted rules, and one interaction accent. Do **not** adopt ZEGGO orange: orange would conflict with Sentiment Pulse’s existing HOLD/caution meaning. Preserve green/amber/red solely for financial status semantics. |
| Whitespace and surfaces | Visual elements sit directly on the canvas; the site relies on negative space and sparse structural lines rather than a field of cards. | Remove the current glass-card repetition and use section boundaries, hairline rules, and a small number of opaque surfaces. Information-dense articles retain clear grouping and readable separation. |
| Motion and interaction | Full-screen scroll choreography, 3D wireframe environments, a reflective 3D object, counter-like loading/section moments, and fixed nav make the marketing story feel immersive. | Adapt only the *discipline* of paced reveal: short, state-driven transitions and a stable header. Do not copy or introduce 3D, WebGL, GSAP, Three.js, scrollytelling, scroll-jacking, decorative counters, or nonessential full-screen transitions; they would impair financial scanning, performance, reduced-motion support, and the UI-only scope. |
| Micro-interaction | The reference uses subtle state changes in navigation, section progression, and animation timing to make a sparse surface feel responsive. | Use concise focus, hover, press, progress, and disclosure states. They must confirm a current UI state—not create spectacle or delay access to a result. |

#### Explicit non-copy rules

Do not reuse ZEGGO’s wordmark, logo/wifi mark, HVAC subject matter, orange palette, imagery, 3D models, wireframe interiors, loading counter, page composition, copy, fixed navigation pattern, source code, or motion sequences. The reference is a source of principles—restraint, type-led hierarchy, negative space, and deliberate pacing—not a visual template.

### 1.2 Principles translated from ZEGGO’s direction

| Reference quality | Translation for Sentiment Pulse | Guardrail |
|---|---|---|
| Editorial composition | A wide breathing masthead and a clear lead “signal” composition | Never bury the disclaimer or market-status context. |
| One-accent restraint | Neutral surfaces, one cobalt interaction accent, semantic colour only for decision/evidence direction | BUY, HOLD, and SELL remain text/icon-labelled, never colour-only. |
| Deliberate whitespace | Fewer nested containers, 8 px rhythm, and generous section boundaries | Dense evidence remains readable and available without extra fetches. |
| Large type as hierarchy | Display scale is limited to ticker, score, and verdict | Numeric values retain tabular monospaced figures. |
| Pacing without theatre | Short opacity/colour/transform feedback aligned to state changes | No 3D, scroll-jacking, parallax, cursor effects, or motion that obscures live state. |

### 1.3 Current codebase audit

#### Confirmed stack and delivery path

- Frontend: React 19, TypeScript, Vite 6, CSS in one authored stylesheet, `lucide-react`, Vitest, Testing Library, ESLint, and `jsx-a11y`.
- Source entry: `frontend/src/main.tsx` mounts `App` to `#root`; it imports Inter, JetBrains Mono, Plus Jakarta Sans, and `frontend/src/styles/index.css`.
- UI composition: `App.tsx` composes `Header`, `SearchBar`, conditional `LoadingStepper`, conditional `SessionWindowBanner`, `DecisionHero`, `RationaleSection`, `EvidenceExplorer`, `TelemetryDrawer`, and `HistorySidebar`.
- Styling: the only app stylesheet is `frontend/src/styles/index.css`; it uses global custom properties plus reusable class names and a number of component-local inline styles.
- Backend boundary: frontend calls `/api/v1` via `frontend/src/services/api.ts`, consumes job progress through SSE, and receives generated schema types from `frontend/src/api/schema.d.ts`. This boundary is strictly out of scope.
- Build: `npm run build` runs `tsc && vite build` and writes the production bundle to `app/static`. CI requires the built `app/static` output to be committed and match the Vite build.
- Baseline branch/worktree: `main...origin/main`, clean at inspection time. CI uses Node 20 and runs `npm ci`, schema-generation drift check, typecheck, lint, Vitest, build, and static-bundle diff verification.

#### Current UI strengths to retain

- The product already represents the full analysis lifecycle: empty, submission, live multi-stage progress, error, result, no-news, degraded-data, filtered evidence, excluded evidence, telemetry, and recent-history states.
- The existing page is semantically close to a useful reading sequence: search → session context → decision → rationale → evidence → telemetry/history.
- Every decision is accompanied by explainability data and a visible research disclaimer; external article links already use `target="_blank"` with `rel="noopener noreferrer"`.
- The current stylesheet has a global `:focus-visible` rule and a `prefers-reduced-motion` override that should be strengthened, not removed.

#### Problems the redesign must solve

| Area | Observed problem | Redesign response |
|---|---|---|
| Visual hierarchy | Multiple radial backgrounds, gradients, glow shadows, translucent cards, badges, icons, and coloured borders all compete. The verdict is prominent but not uniquely so. | Flat opaque surfaces, one hairline border system, one information accent, and a clearly dominant verdict/ticker zone. |
| Container nesting | Search, hero metrics, facts, rationale, evidence cards, exclusions, telemetry, and history all reuse the same glass-card treatment. | Create only three surface levels: canvas, section, inset. Use separators and spacing before creating another card. |
| Typography | Three families and frequent all-caps labels make nearly every label feel important. Inline styles fragment scale and colour decisions. | Use Inter for UI/editorial text and JetBrains Mono only for symbols, timestamps, scores, and technical values. Adopt an explicit type scale and move presentation-only inline styles into CSS. |
| Colour semantics | Cyan is branding, focus, publisher metadata, progress, links, and selected state. Red, amber, and green are also heavily glowed. | Cobalt is interaction only; semantic colours are limited to decision and score meaning. Pair each with text/icon/shape. |
| Reading flow | Raw telemetry has equal visual treatment to explanatory evidence, and every article exposes all probability values immediately. | Put result/evidence quality first; use a compact article default and show score detail on hover/focus or an explicit disclosure without hiding any data permanently. |
| Form clarity | The ticker input depends on its placeholder rather than a persistent visible label. Advanced controls compete with primary entry. | Add a visible label and helper line; retain both toggles but frame them as secondary run options. |
| Filter semantics | Filter buttons are visually tabs but do not expose tab roles, `aria-selected`, or a labelled result region. | Preserve filter state/logic but add presentational ARIA semantics and visible selected indicator. |
| Mobile | Only header/search have a narrow breakpoint. The 36 px hero padding, verdict size, horizontally clustered metadata, filter row, FinBERT bar, and inline metric patterns can crowd or wrap poorly. | Define layouts at 1440, 1024, 768, and 375 px; stack metadata, make filter control horizontally scrollable only as a last resort, and preserve touch targets. |
| Live updates | The progress message is visually clear but has no designated live region; the clocks update every second and need not be announced. | Give only the meaningful analysis status a polite live region; mark decorative/live clock updates non-announcing. |
| Accessibility | Muted text/border opacity on dark glass may not meet contrast everywhere; active state and direction lean too heavily on colour; focus is generic and some hit areas are below the recommended 44 px target. | Target WCAG 2.2 AA (minimum 4.5:1 normal text, 3:1 large text/non-text UI); use explicit focus ring, labels/icons, 44×44 px pointer targets, source order matching visual order, and reduced motion. |

### 1.4 External best-practice findings applied

- W3C’s [WCAG 2.2](https://www.w3.org/TR/wcag/) requires, among other things, a 4.5:1 contrast ratio for normal text at AA and that colour not be the sole means of conveying information. Its current focus guidance also supports a high-contrast, visible focus treatment. This plan uses written verdict labels, direction icons, and score signs in addition to colour.
- The [GOV.UK dashboard guidance](https://brand.design-system.service.gov.uk/data/dashboards/) recommends a careful hierarchy, concise guidance, and avoiding an undifferentiated collection of indicators; its [chart colour guidance](https://brand.design-system.service.gov.uk/colour/charts/) recommends a deliberately limited palette and non-colour encodings. The sentiment decision is therefore a single lead indicator with quality/context immediately beside it, while detailed evidence follows below.
- Do not add a chart library: this UI has no historical time series or new data shape to plot. A fabricated trend chart would imply analysis the product does not perform and violate the UI-only constraint.

## 2. Design concept and principles

### Concept: “Signal, then proof”

The product is not a trading terminal and must not visually overstate the model’s certainty. It is a research surface that leads with an algorithmic classification, then makes the supporting conditions and source evidence easy to audit. The design should feel confident in craft but measured in claims.

1. **One primary signal.** The ticker and BUY/HOLD/SELL classification form the focal point; confidence, quality, and corroboration are supporting proof, not competing hero cards.
2. **Evidence before decoration.** Use space, type, and hierarchy instead of glass, blur, gradients, and glow.
3. **Semantic colour has a budget.** Green, amber, and red are reserved for model direction/status. Blue is reserved for interactive affordance and active selection. Everything else is neutral.
4. **Dense content earns disclosure.** A headline, source, date, score sign, and compact sentiment indicator are always visible. Probability breakdown, lead text, effective weight, and excluded groups expand progressively without changing their data or fetch behavior.
5. **Quiet motion communicates state.** Motion confirms an interaction or state transition; it does not decorate static content or introduce a new timing dependency.
6. **Responsive means reordered, not merely shrunk.** Source order stays meaningful; layout moves from editorial grid to a single readable column.
7. **Trust is visual.** The permanent disclaimer, session boundary, cached/degraded/no-news state, and confidence caveats remain explicit and close to the result.

## 3. Target design system

### 3.1 Theme decision

Ship **one refined dark theme** in this overhaul. A light theme or a theme switcher would add behaviour and user preference persistence that do not currently exist; it is not recommended under the hard constraint. Keep all tokens semantic so a future approved light theme can be added without component rewrites.

### 3.2 Ready-to-use token layer

Replace the existing root token block with the following semantic layer, then map existing compatibility names (for example `--accent-cyan`, `--buy-green`) to the new variables during the transition. Do not remove old aliases until every existing component class and inline `var(...)` reference has been migrated and verified.

```css
:root {
  color-scheme: dark;

  /* Canvas and surfaces */
  --color-canvas: #10100f;
  --color-canvas-raised: #171715;
  --color-surface: #1c1c1a;
  --color-surface-hover: #242421;
  --color-surface-pressed: #2b2b27;
  --color-inset: #151513;
  --color-scrim: rgb(16 16 15 / 88%);

  /* Ink */
  --color-ink: #f4f2ed;
  --color-ink-soft: #c8c5bc;
  --color-ink-muted: #99968d;
  --color-ink-faint: #6f6d66;
  --color-on-accent: #ffffff;

  /* Lines and interaction */
  --color-line: #35352f;
  --color-line-strong: #57574f;
  --color-line-subtle: #292925;
  --color-accent: #75a7ff;
  --color-accent-strong: #9dbdff;
  --color-accent-wash: rgb(117 167 255 / 12%);
  --color-focus-outer: #f4f2ed;
  --color-focus-inner: #10100f;

  /* Meaning: use only with text/icon/sign */
  --color-positive: #6fd29b;
  --color-positive-ink: #b7f2cd;
  --color-positive-wash: rgb(111 210 155 / 12%);
  --color-caution: #f4c776;
  --color-caution-ink: #ffe3a8;
  --color-caution-wash: rgb(244 199 118 / 13%);
  --color-negative: #f28b86;
  --color-negative-ink: #ffc1bb;
  --color-negative-wash: rgb(242 139 134 / 12%);
  --color-info: #8cb4ff;
  --color-info-wash: rgb(140 180 255 / 12%);

  /* Type */
  --font-ui: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-data: "JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  --font-size-00: 0.75rem;  /* 12 */
  --font-size-0: 0.8125rem; /* 13 */
  --font-size-1: 0.875rem;  /* 14 */
  --font-size-2: 1rem;      /* 16 */
  --font-size-3: 1.125rem;  /* 18 */
  --font-size-4: 1.375rem;  /* 22 */
  --font-size-5: clamp(2.25rem, 5vw, 4.5rem);
  --font-size-score: clamp(2rem, 4vw, 3.5rem);
  --line-tight: 1.08;
  --line-title: 1.2;
  --line-body: 1.55;
  --tracking-label: 0.08em;

  /* Spatial scale: 4 px base */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;
  --space-16: 4rem;

  /* Shape, line, elevation */
  --radius-1: 0.375rem;
  --radius-2: 0.625rem;
  --radius-3: 0.875rem;
  --radius-pill: 999px;
  --border-default: 1px solid var(--color-line);
  --border-strong: 1px solid var(--color-line-strong);
  --shadow-none: none;
  --shadow-float: 0 16px 40px rgb(0 0 0 / 24%);

  /* Layout */
  --content-max: 90rem;
  --content-gutter: clamp(1rem, 3vw, 2.5rem);
  --section-gap: clamp(2rem, 5vw, 4.5rem);

  /* Motion */
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --duration-fast: 120ms;
  --duration-base: 180ms;
  --duration-enter: 240ms;
}
```

### 3.3 Typography and numbers

| Role | Token/weight | Use |
|---|---|---|
| Product name | Inter 600, `--font-size-1`, uppercase, `--tracking-label` | Header wordmark only. |
| Page/section eyebrow | Inter 600, `--font-size-00`, uppercase, `--tracking-label` | “Analysis”, “Evidence”, “Method”. |
| Section title | Inter 600, `--font-size-4`, `--line-title` | Once per major section. |
| Asset ticker | Inter 600, `--font-size-5`, `--line-tight`, -0.04em | Main result identity. |
| Verdict | Inter 600, `--font-size-4` | Compact labelled chip/block; no shouty 2.8 rem pill. |
| Metric value | JetBrains Mono 500, `--font-size-score` or `--font-size-3`, `font-variant-numeric: tabular-nums` | Scores, percentages, weight, timestamps. |
| Body | Inter 400, `--font-size-2`, `--line-body` | Rationale, fact, article lead. |
| Metadata | Inter 500, `--font-size-0`, line-height 1.35 | Publisher, source, labels. |

Do not use all caps for sentence text, article headlines, or action labels. Use `font-variant-numeric: tabular-nums` in `.font-mono`, score/value, clocks, and telemetry. Retire the Plus Jakarta Sans imports and its `--font-display` assignment only after its visual role is migrated to Inter; keep the installed source font packages until a clean `npm ci`, build, and static-bundle review proves lockfile/build consistency.

### 3.4 Icons

Continue using the installed `lucide-react` package. Icons are 16 px by default, 18 px in section headers, and 20 px only for primary actions or result direction. Always pair non-decorative icons with visible text or an accessible name. Do not introduce filled illustration sets, emoji, custom SVG logo art, or a second icon library.

### 3.5 Motion and micro-interaction rules

- Keep CSS transitions; **do not add a runtime animation library**. The app’s transitions are simple and self-contained, and Motion’s own [React guidance](https://motion.dev/docs/react) says CSS is appropriate for these effects.
- Allowed: surface/background/border colour transition; 1–2 px lift only on clickable cards; disclosure opacity/height; 4 px maximum entry translate for newly rendered result sections; progress fill width.
- Durations: 120 ms press/colour, 180 ms hover/focus/disclosure, 240 ms entry. Use `--ease-out`.
- No looping decorative animation except the existing pipeline spinner while a job is in progress. Keep it meaningful and stop it at reduced motion.
- `@media (prefers-reduced-motion: reduce)` must set all nonessential animations/transitions to none/near-instant, retain progress information as text, and avoid transform movement.
- Hover is enhancement only; `:focus-visible` and touch states communicate the same change. Never use scale/translate that shifts neighbouring content.

## 4. Information architecture and layout specification

### 4.1 Desktop grid and page order

At ≥1200 px, use a max-width 1440 px content area with a 12-column grid, 24 px gutters, and 24 px column gaps. At 1024–1199 px use 12 columns/20 px gaps. At 768–1023 px use 8 columns/20 px gaps. Below 768 px use one column/16 px gutter.

```text
Permanent legal notice
Product masthead                         clocks
────────────────────────────────────────────────
Analysis input + run options             (12 cols)
Loading state OR result context          (12 cols)
Asset / verdict / key signal             (12 cols)
  key metrics                            (12 cols; 4 equal cells)
Method + facts                           (6 cols / 6 cols)
Evidence                                 (12 cols)
Technical run details                    (12 cols, quiet disclosure)
Recent queries                           (12 cols, quiet disclosure)
```

Keep DOM order exactly aligned to this sequence. Do not make the history drawer a fixed sidebar: its current state/placement is in-page and moving it to a new navigation paradigm risks a feature-behaviour change.

### 4.2 Responsive rules

| Breakpoint | Required layout behaviour |
|---|---|
| ≥1200 px | 12-column grid. Hero identity/verdict align on one row; metric cells are four columns. Facts/rationale are two equal columns. |
| 1024–1199 px | Same information order; hero may wrap verdict under identity only if necessary. Keep metrics 2×2 or 4-up if cells stay ≥180 px. |
| 768–1023 px | Eight-column grid. Header clocks move below brand. Hero becomes identity then verdict. Metrics 2×2. Facts/rationale stack. |
| <768 px | One column. 16 px gutters; header in two orderly rows; input and run button stack; 48 px controls; hero padding 20 px; metrics one per row or 2×2 only when at least 156 px wide; filter control wraps to two rows before horizontal scrolling; article metadata becomes a two-line grid. |
| 320–374 px | No clipping or horizontal page scroll. Never truncate verdict, warning heading, score sign, ticker, source name, or button label; lower-priority provider/weight may wrap. |

## 5. Component-by-component redesign specification

### 5.1 `Header.tsx`: legal notice and masthead

**Layout:** keep `#legal-disclaimer-strip` at the top and always visible in normal page flow. Restyle it as a compact opaque notice: 12 px vertical padding, caution-tint left rule, 13 px text, warning icon, and no translucent red wash. Keep the exact legal wording and strong opening phrase. The sticky `.app-header` below becomes a 72 px masthead with an off-white typographic wordmark, a small “REAL-TIME MARKET SENTIMENT” eyebrow, no gradient icon tile, no text gradient, and a single hairline lower border.

**Clocks:** retain ET and UTC values/IDs. Render as understated data pairs with a neutral status dot and visually hidden/static “Eastern Time”/“UTC” context where necessary. Clock text must not use an ARIA live region; the analysis status is the meaningful live update. On mobile, put clocks in a second row with even spacing.

**States:** sticky header background becomes opaque `--color-scrim` with a subtle blur only if contrast remains reliable; no shadow. It must never cover a keyboard focus target (WCAG 2.2 focus-not-obscured check).

### 5.2 `SearchBar.tsx`: analysis command surface

**Layout:** replace the glass panel with a flat section surface. Add a visible `<label>` associated with `#ticker-search-input` reading “Asset symbol”; retain existing placeholder. Make the input the wide primary control and put the existing `#run-analysis-btn` inline at desktop, full-width below input on narrow screens. Place the quick chips on their own low-emphasis row. Group existing checkboxes under visible “Run options” text; do not alter their default values, `title`, checked state, disabled state, or callback arguments.

**Visual treatment:** 52 px desktop/48 px mobile input and button height; line border, 10 px radius; focus uses the token two-colour ring. The primary button is solid cobalt, not a gradient. Quick chips are plain outlined buttons with symbol values in mono. Checked options use a visible label/icon/check state, not cyan alone.

**States:**

- Default: helper text says supported formats (equities, ETFs, forex, futures, crypto), not an additional validation rule.
- Empty/invalid-as-today: preserve existing disabled submit rule; style disabled control with sufficient text contrast.
- Loading: preserve all disable behaviour and `ANALYZING…` content; spinner may rotate only when motion is permitted.
- Hover/pressed/focus: change border/surface, no glow.
- Screen reader: label, checkbox labels, and current button label remain exposed; do not replace buttons with divs.

### 5.3 `LoadingStepper.tsx`: live analysis progress

**Layout:** turn the current six-card grid into a restrained process band: title and percentage row, linear progress line, then a responsive ordered stage list. Desktop may show six inline nodes joined by hairlines; tablet shows three per row; mobile shows six compact list rows. The current stage has cobalt line/icon; completed stages have an explicit check icon and “Complete” text visually available on narrow screens; pending stages are neutral.

**States and accessibility:** preserve stage keys, percentage calculation, stage labels, and `#analysis-stepper`. Add `role="status"`/`aria-live="polite"` only to the concise dynamic message and percentage, avoiding repeated announcement of the full stage list. `aria-valuemin`, `aria-valuemax`, and `aria-valuenow` belong on the visual progressbar. Reduced motion removes spinner rotation but not its “in progress” label.

### 5.4 `SessionWindowBanner.tsx`: analysis context strip

**Layout:** place this immediately above the hero as a compact, non-card context row. The session type, market open/closed status, and lookback are primary; ET, UTC, and run timestamp follow in lower-weight mono metadata. Use a 3 px semantic left rule—green for open, amber for closed—not a cyan border.

**Responsive:** at desktop, distribute identity/context and timestamps; below 768 px, form a two-row definition-list-like layout. Never hide the time boundary or run timestamp.

**States:** retain current fallback/formatting. OPEN/CLOSED must include text and status icon, not colour only. Keep all titles and all session fields.

### 5.5 `DecisionHero.tsx`: the signal card

**Layout:** use a single, opaque hero section with no gradient, glow, or oversized pill. Top-left: “Current algorithmic classification” eyebrow, ticker, company name, asset type, and existing cache/data status labels. Top-right: a compact verdict block with icon, explicit BUY/HOLD/SELL label, and visible HOLD reason beneath it. On mobile the verdict follows identity rather than being visually squeezed beside it.

**Metrics:** below a single separator, display the four existing metrics as equal definition-list cells: label, tabular number/status, compact explanation. Composite sentiment receives the most contrast; confidence, evidence quality, and corroboration remain secondary. Preserve all values, threshold branches, labels, support-source count, `n/a` behavior, score formatting, and IDs. Use a one-pixel top border rather than four mini glass cards.

**Warnings and disclaimer:** show NO FRESH NEWS, NO RELEVANT NEWS, and DEGRADED INGESTION directly after the identity/verdict row and before metrics, using the existing exact messages and roles. Give each an icon + text + semantic border/background. Keep `.heuristic-footnote` immediately beneath metrics, fully visible, with the `result.disclaimer` string intact; visually distinguish it as a clear “Research use only” notice rather than an easily missed low-contrast footer.

**State rules:**

- BUY: `--color-positive` only on the verdict rule/icon/score and status label; never a green page/card wash.
- HOLD: `--color-caution`; HOLD reason remains explicit.
- SELL: `--color-negative`; never encode SELL only through red.
- Cached, no-news, no-relevant-news, and degraded labels retain their existing text and conditions.
- Initial loading does not render a stale hero; preserve the current conditional rendering.

### 5.6 `RationaleSection.tsx`: method and observed facts

**Layout:** where an LLM summary exists, render `#llm-synthesis-card` first as a compact “Catalyst synthesis” note with model label, a quiet indigo/info rule, and body text. It must remain conditional on `llmSummary` exactly as today. Below it, retain `#rationale-grid`: observed facts at left and synthesized rationale at right; remove inner glass treatment and use section-level surfaces separated by a vertical rule on desktop/horizontal rule on tablet and mobile.

**Observed facts:** each fact has statement first, then publisher/date/category/impact in a compact metadata row. Use an impact word plus small arrow/icon and colour. Avoid turning every metadata value into a pill; use one category label and text separators. Empty state remains in the same space with its current message.

**Synthesized rationale:** retain summary first, then inferences as a labelled list. The “Formula & Sentiment Drivers” phrase remains visible, but is lower-weight metadata—not a competing badge. Do not alter citation map construction, fact keys, date formatting, or inference content.

### 5.7 `EvidenceExplorer.tsx`: audit trail with progressive disclosure

**Layout:** this is the one large evidence section. Header has eyebrow “Evidence”, title/count, and filter control. Filters retain the exact ALL/POSITIVE/NEGATIVE/NEUTRAL states and count logic. Style them as a segmented control with a 2 px selected underline and text/score-sign differentiation. Add `role="tablist"`, `role="tab"`, `aria-selected`, and a labelled `role="region"` for the controlled list only if they accurately reflect the existing in-page filter behaviour; retain native buttons and click handlers.

**Retained article default row:**

1. headline link (or existing non-link fallback) and external-link icon;
2. source, provider, date, age, and weight in a responsive metadata grid;
3. directional score shown as signed mono value with a labelled semantic indicator;
4. a compact three-part Pos/Neu/Neg bar whose segments also retain the existing textual percentages.

Make lead text and full probability/weight detail a per-article disclosure at initial render **only if** it can be driven by local presentation state without changing article data, filter behavior, URL link behavior, or element hooks. If implementation scope must stay minimal, keep them visible in their current DOM order but style them as lower-weight detail; do not omit them. No lazy-loading, pagination, sorting, new data fields, or article-limit rule is allowed.

**Excluded articles:** retain current `showExcluded`, grouping, count calculations, `aria-expanded`, `aria-controls`, and `#excluded-articles-list`. Restyle as a lower-emphasis “Excluded from scoring” disclosure with neutral/caution rule, reason heading, count, and article rows. Excluded content must be keyboard-discoverable when expanded and never silently removed.

**States:**

- Empty filtered state retains the exact message; centre it in a 120 px minimum area with a neutral icon, not a blank card.
- Zero retained/no-news remains accurately represented by parent hero and evidence empty state.
- Article hover/focus changes border/surface only; no horizontal translate that makes list rows jitter.
- Long headlines wrap; URLs never show raw unless present as text already; external link target/rel unchanged.

### 5.8 `TelemetryDrawer.tsx`: technical detail

**Layout:** keep `#pipeline-telemetry-strip` and all five data points, but recast it as a collapsed-by-default `details`/summary-style “Run details” section **only if the existing always-visible telemetry is deemed presentation-only and its DOM content remains mounted/accessible**. To eliminate ambiguity under the hard constraint, the default implementation is safer: leave it expanded and style it as a quiet five-column (desktop), two-column (tablet), one-column (mobile) definition list below Evidence. Do not add a new persistence setting.

**Visual rules:** technical labels are `--font-size-00`, values mono `--font-size-0`; no dark pseudo-card. Highlight cache status with text and a small info status, not saturated cyan. Preserve latency, counts, cost, token count, model strings, fallbacks, and every calculation.

### 5.9 `HistorySidebar.tsx`: recent queries

**Layout:** retain its existing conditional rendering and local open/closed state. Style `#recent-history-panel` as the final low-priority section with an outline-only toggle and a text chevron. The expanded grid is a list of concise buttons, not glass cards: ticker + verdict/status at left; UTC time and arrow at right.

**States:** preserve `aria-expanded`, `aria-controls`, `#recent-history-grid`, query refresh, disabled/loading behavior as currently implemented, historical run click behavior, asset display, data status labels, and UTC format. Use semantic verdict icon/text in addition to badge colour. On mobile each history button stacks data with a 44 px minimum target.

### 5.10 `App.tsx`: page frame, empty, and error states

**Layout:** retain component order and all conditionals. Replace decorative radial page background with `--color-canvas`; set `.main-content` max width from token and section gaps from `--section-gap`. Add a visually available page heading context only if it does not duplicate the existing H1/brand hierarchy. Do not add a side navigation.

**Error:** retain existing condition and message. Move the inline presentation styles into a named `.analysis-error` class, preserving AlertCircle, text, and red semantic role. Error surface must have clear alert icon/text and a recovery cue that does not invent a retry action.

**Empty:** retain existing copy and icon. Reframe it as a quiet introduction panel with supported asset examples shown in current text; do not add onboarding slides, auto-run samples, or new actions.

## 6. Accessibility and interaction requirements

1. Meet WCAG 2.2 AA baseline: 4.5:1 normal text, 3:1 large text and essential graphical objects; test text against the actual opaque surface, not an assumed canvas behind transparency.
2. Add a two-colour `:focus-visible` ring (`2 px` outer + `2 px` gap/inner contrast) on links, buttons, inputs, checkboxes, filters, history entries, and disclosures. Do not remove native focus without replacement.
3. Ensure every pointer control has a 44×44 px target or equivalent 24 px target-size/spacing treatment; quick chips can have visible padding that reaches this target.
4. Give `#ticker-search-input` a persistent label. Keep placeholder as an example only. Do not alter its `maxLength`, uppercase transform, value, or disabled condition.
5. Use semantic `<button>`/`<a>` elements already present. Never make card containers clickable where their internal link/button has different behaviour.
6. Add only meaningful live semantics: the analysis message/progress may be polite; errors remain alerts; do not announce second-by-second clocks or animate counts.
7. Ensure filter selected state is available to keyboard and assistive technology. The buttons must be reachable in a logical left-to-right order; Enter/Space activate them.
8. Keep logical source order after every grid/reorder breakpoint. Do not use CSS `order` to create a visual sequence that diverges from DOM reading order.
9. Display decision direction with text (BUY/HOLD/SELL), sign/icon, and colour; impact and market status likewise require text/icon, not colour alone.
10. Keep existing `prefers-reduced-motion` support and broaden it to new disclosure/entry transitions. Do not autoplay media or use parallax.
11. Check at 200% zoom, keyboard-only navigation, and 320 px wide viewport. No horizontal page scroll, obscured focus, clipped legal notice, or inaccessible disclosure is acceptable.

## 7. Do Not Touch — functional hooks, data boundaries, and stable selectors

### 7.1 Prohibited functional changes

Do not edit these files for the redesign except to confirm they remain untouched:

- `app/**`, `alembic/**`, `tests/**` backend/contract/e2e fixtures, and all Python configuration.
- `frontend/src/services/api.ts`, `frontend/src/api/events.ts`, `frontend/src/api/openapi.json`, `frontend/src/api/schema.d.ts`, `frontend/src/types.ts`, `frontend/src/utils/formatters.ts`, and `frontend/src/utils/time.ts`.
- Any `handleSearch`, `handleSelectHistoricalRun`, SSE subscription/unsubscription, cache/error/stale-request handling, request arguments, API URL, generated type, data calculation, condition, default toggle value, format function, or result field read.

### 7.2 Preserve exactly: IDs, ID relationships, and test hooks

Do not rename, delete, duplicate, or move these IDs outside their current semantic component. Preserve their element type where it is an input/button/form target. Preserve the `aria-controls` pairs.

| Component | Stable hook(s) |
|---|---|
| `main.tsx` | `#root` mount target |
| `Header.tsx` | `#legal-disclaimer-strip`, `#header-clock-et`, `#header-clock-utc` |
| `SearchBar.tsx` | `#search-section`, `#ticker-search-input`, `#run-analysis-btn`, `#force-refresh-checkbox`, `#enable-llm-checkbox`; generated quick-chip IDs: `#quick-chip-nvda`, `#quick-chip-aapl`, `#quick-chip-eur-usd`, `#quick-chip-usd-jpy`, `#quick-chip-gc-f`, `#quick-chip-btc-usd` |
| `LoadingStepper.tsx` | `#analysis-stepper` |
| `SessionWindowBanner.tsx` | `#session-window-banner` |
| `DecisionHero.tsx` | `#decision-hero-card`, `#result-ticker-symbol`, `#result-verdict-pill`, `#result-composite-score`, `#result-confidence-score` |
| `RationaleSection.tsx` | `#rationale-section`, `#llm-synthesis-card`, `#rationale-grid`, `#synthesized-rationale-text` |
| `EvidenceExplorer.tsx` | `#evidence-explorer`, `#excluded-articles-list`; preserve the exclusion button’s `aria-controls="excluded-articles-list"` and `aria-expanded` logic |
| `TelemetryDrawer.tsx` | `#pipeline-telemetry-strip` |
| `HistorySidebar.tsx` | `#recent-history-panel`, `#recent-history-grid`; preserve toggle `aria-controls="recent-history-grid"` and `aria-expanded` logic |

### 7.3 Preserve CSS/behavioural class contract during migration

All existing class names below are styling hooks today; several also encode application state or are used by tests. Do not rename them in this overhaul. Restyle them in place, and add new `.sp-*` classes only when a genuinely new presentational sub-element is needed.

- Test/interaction selectors: `.search-form` (queried in `App.test.tsx`), `.history-item-row` (used by `closest()` in `App.test.tsx`), `.history-toggle-btn`, `.filter-tab`, `.filter-tab.active`.
- Render/state classes: `.hero-decision-card`, `.hero-decision-card.buy`, `.hero-decision-card.hold`, `.hero-decision-card.sell`, `.verdict-pill`, `.verdict-pill.buy`, `.verdict-pill.hold`, `.verdict-pill.sell`, `.stage-node`, `.stage-node.active`, `.stage-node.completed`, `.no-fresh-news-banner`, `.no-fresh-news-banner.degraded`, `.badge-buy`, `.badge-hold`, `.badge-sell`, `.badge-neutral`, `.animate-fade-in`, `.animate-spin-slow`.
- Shared layout/utility classes: `.app-container`, `.main-content`, `.glass-panel`, `.font-display`, `.font-mono`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-chip`, `.btn-link`, `.disclaimer-strip`, `.app-header`, `.header-brand`, `.brand-icon`, `.brand-title`, `.brand-subtitle`, `.header-clocks`, `.clock-item`, `.clock-dot`.
- Search/progress classes: `.search-section`, `.search-form`, `.search-input-wrapper`, `.search-icon`, `.search-input`, `.search-options`, `.quick-chips-group`, `.quick-chips-label`, `.toggles-group`, `.custom-checkbox`, `.stepper-card`, `.stepper-header`, `.stepper-title`, `.progress-track`, `.progress-bar-fill`, `.stages-grid`, `.stage-node-icon`, `.stage-node-label`.
- Result/rationale/evidence classes: `.session-banner`, `.session-info`, `.session-badge`, `.session-time-text`, `.decision-top`, `.asset-identity`, `.asset-ticker-row`, `.asset-ticker`, `.asset-exchange`, `.asset-name`, `.verdict-box`, `.hold-reason-sub`, `.metrics-strip`, `.metric-item`, `.metric-label`, `.metric-val`, `.metric-sub`, `.heuristic-footnote`, `.rationale-section`, `.rationale-grid`, `.section-card`, `.section-header`, `.section-title`, `.facts-list`, `.fact-item`, `.fact-meta`, `.fact-publisher`, `.rationale-body`, `.evidence-section`, `.evidence-controls`, `.filter-tabs`, `.article-list`, `.article-card`, `.article-card-header`, `.article-title-link`, `.article-title-text`, `.article-meta-row`, `.finbert-breakdown-bar`, `.score-pos`, `.score-neu`, `.score-neg`, `.excluded-articles-wrapper`, `.excluded-group`.
- Detail/empty classes: `.telemetry-strip`, `.telemetry-cell`, `.empty-state`, `.empty-state-icon`.

The legacy names may sound glass/neon-specific; retaining the class selectors is intentional compatibility, not a visual endorsement. Their CSS definitions change to the system above.

## 8. Resources and licensing

| Resource | Decision | Exact source / command | Licence and compatibility |
|---|---|---|---|
| Inter | Retain as the sole UI/display family. Already installed as `@fontsource/inter@^5.3.0`. | [Inter upstream](https://github.com/rsms/inter); no installation required. If package integrity is restored: `cd frontend; npm install @fontsource/inter@^5.3.0` | SIL OFL 1.1, free for commercial use; React/Vite-compatible. |
| JetBrains Mono | Retain for financial/data values only. Already installed as `@fontsource/jetbrains-mono@^5.3.0`. | [JetBrains Mono upstream](https://github.com/JetBrains/JetBrainsMono); no installation required. If restored: `cd frontend; npm install @fontsource/jetbrains-mono@^5.3.0` | Typeface is SIL OFL 1.1; free for commercial/non-commercial use; React/Vite-compatible. |
| Plus Jakarta Sans | Retire from runtime imports after migration; do not replace it with another display face. | Existing package: `@fontsource/plus-jakarta-sans@^5.3.0`; upstream [licence record](https://github.com/google/fonts/blob/main/ofl/plusjakartasans/upstream_info.md). Remove only via normal dependency update after build verification. | SIL OFL; no new licensing burden, but removing a redundant family reduces payload and visual noise. |
| Lucide React | Retain; it already supplies every required icon category. | [Lucide icons](https://lucide.dev/icons); existing `lucide-react@^1.16.0`; no installation required. | ISC (with noted Feather-derived MIT icons), permissive and React-compatible. |
| CSS transitions | Select as the motion implementation. | No package; use native CSS and `prefers-reduced-motion`. | No licence/dependency; compatible with React 19/Vite 6. |
| Motion for React | Explicitly **not selected** for this phase. | [Motion React installation](https://motion.dev/docs/react-installation); do not run `npm install motion`. | Free MIT and React 18.2+ compatible, but unnecessary for the limited state feedback required here. |
| Playwright Test | Add only as a development visual-regression tool in Phase 6. | [Official Playwright docs](https://playwright.dev/docs/intro): `cd frontend; npm install -D @playwright/test`; `npx playwright install chromium` | Apache-2.0; supports Vite and screenshot tests. It is dev-only and has no production UI/runtime effect. |

Never load fonts from a third-party CDN. Existing Fontsource imports package and build assets locally, matching the current Vite output model. Preserve required licence notices in installed package metadata; do not copy icon SVGs into the codebase unnecessarily.

## 9. File-by-file change map

| File | Change | Functional boundary |
|---|---|---|
| `frontend/src/styles/index.css` | Primary work: replace neon/glass visual rules with tokens, grid, components, responsive layouts, focus/reduced-motion rules; retain every existing class selector listed above. | CSS presentation only. No selector deletion/rename in Phase 1. |
| `frontend/src/main.tsx` | Remove Plus Jakarta Sans imports after CSS no longer uses it; retain React mount and Inter/JetBrains imports. | Do not alter `ReactDOM.createRoot`, `#root`, StrictMode, or import order needed for app mounting. |
| `frontend/src/App.tsx` | Replace error and empty-state inline presentation with named presentational classes; optionally add non-invasive section wrapper/ARIA labels. | Do not change any state, handlers, conditionals, component order, API calls, error content, or result props. |
| `frontend/src/components/Header.tsx` | Add presentation-only classes/ARIA attributes such as non-announcing clock treatment; retain DOM hierarchy/IDs/text/time effect. | Do not alter interval, ET/UTC calculation, disclaimer copy, IDs, or icon intent. |
| `frontend/src/components/SearchBar.tsx` | Add a persistent label/grouping wrappers/classes and, if needed, presentation-only `aria-describedby`. | Do not alter ticker state, render-time active ticker synchronization, toggles/defaults, chips, generated IDs, submit path, calls, max length, disabled logic, titles, or labels. |
| `frontend/src/components/LoadingStepper.tsx` | Add progressbar/live-region semantics and wrappers/classes required by visual process band. | Do not change `STAGES`, keys, calculation, progress width calculation, message, ticker label, or condition logic. |
| `frontend/src/components/SessionWindowBanner.tsx` | Add semantic layout classes/definition grouping. | Do not change fallback session prop, formatting, values, IDs, titles, or open/closed computation. |
| `frontend/src/components/DecisionHero.tsx` | Move presentational inline styles to classes, add grouping/accessible labels, and restructure only around preserved hooks. | Do not change verdict thresholds, `formatScore`, `formatHoldReason`, corroboration/evidence-free decisions, messages, values, result field reads, or disclaimer. |
| `frontend/src/components/RationaleSection.tsx` | Move inline visual styles to classes; add semantic list/group classes. | Do not change facts/inferences map, cited lookup, impact class mapping, conditional LLM synthesis, contents, keys, or format function. |
| `frontend/src/components/EvidenceExplorer.tsx` | Add filter/list semantics and classes; optionally local presentation-only article disclosure. | Do not alter local filter state values, thresholds, counts, filtering, excluded grouping/counts, URLs/rel, slices, weights, IDs, or `showExcluded` behaviour. |
| `frontend/src/components/TelemetryDrawer.tsx` | Classes/definition-list markup only. | Do not change calculated fallback values or remove any of the five cells. |
| `frontend/src/components/HistorySidebar.tsx` | Classes/layout and optional chevron icon presentation only. | Do not alter fetch, refresh effect, conditional `null`, `isOpen`, selection callback, UTC formatter, IDs/ARIA pairs, history value logic. |
| `frontend/src/App.test.tsx`, `frontend/src/components/DecisionHero.test.tsx` | Do not edit to make a regression pass. Add assertions only where semantic/accessibility additions need coverage; preserve existing selectors/assertions. | Any changed existing test indicates a compatibility breach to investigate, not a licence to change the test. |
| `frontend/package.json`, `frontend/package-lock.json` | Only Phase 6 may add `@playwright/test` as a dev dependency. Do not add runtime UI libraries. | Never change existing production dependency versions merely for restyling. |
| `frontend/playwright.config.ts`, `frontend/tests/visual/*.spec.ts` | New, Phase 6 only: screenshot harness/configuration. | Test-only; never mock or alter app logic to create a design state. |
| `app/static/**` | Regenerated only by `npm run build`, committed with source changes because CI enforces parity. | Never hand-edit compiled assets. |

## 10. Branch, commit, review, and merge protocol

1. Start by updating local `main` without modifying it. Create and push integration branch: `git switch -c redesign/minimal-ui origin/main`; `git push -u origin redesign/minimal-ui`.
2. Each phase starts from the integration branch as a small feature branch: `git switch redesign/minimal-ui`; `git switch -c redesign/minimal-ui-pN-<slug>`.
3. Commit convention: Conventional Commit format, narrow and imperative. Examples: `feat(ui): establish minimal dark design tokens`; `feat(ui): redesign signal hero and metrics`; `test(ui): add visual regression coverage`; `docs(ui): record visual QA matrix`.
4. Before pushing any phase: `git status --short`, run the phase checks, review `git diff --check`, `git diff --stat`, and a semantic diff of source. Never include `.env`, data, unrelated generated output, or user changes.
5. Push feature branch: `git push -u origin redesign/minimal-ui-pN-<slug>`. Open a PR targeting `redesign/minimal-ui`, not `main`. The reviewer manually reviews source, generated `app/static` changes, screenshots, and CI.
6. After approval, manually merge the feature PR into `redesign/minimal-ui` using the repository’s preferred merge method. Delete the feature branch only after it has merged and the user confirms normal repository hygiene.
7. When all phases are approved, open one final PR from `redesign/minimal-ui` to `main`. The user reviews and manually merges it. **Do not merge, commit directly to, or push to `main` at any point.**

## 11. Ordered execution plan

### Phase 0 — Freeze baseline and resolve reference record

- **Branch:** `redesign/minimal-ui-p0-baseline`
- **Commit:** `docs(ui): capture redesign baseline and reference status`
- **Files touched:** new `docs/ui-baseline.md` and optionally an appendix to this plan only; no runtime source.
- **Tasks:**
  1. Record `git status --short`, current commit SHA, Node/npm versions, and package-lock checksum.
  2. Run the current frontend checks: `npm ci`, `npm run typecheck`, `npm run lint`, `npm test`, `npm run build` from `frontend`; record pass/fail output and static diff status.
  3. Start the backend/frontend through documented commands and capture baseline screenshots at 1440×900, 1024×768, 768×1024, and 375×812 for: empty, loading, BUY result, HOLD/no-news, SELL/degraded, filter selection, exclusions expanded, and history expanded. Use deterministic test fixtures/mocks only in the test environment; do not change production data.
  4. Re-open the verified [Awwwards ZEGGO entry](https://www.awwwards.com/sites/zeggo) and [ZEGGO live site](https://www.zeggo.com.sg/) once; record a reference screenshot and confirm the implementation will follow Section 1.1’s translations and non-copy rules.
- **Acceptance criteria:** baseline checks pass or known failures are documented before any visual work; no app source/generated bundle edits; the reference record and explicit non-copy boundary are available to reviewers.

### Phase 1 — Establish minimal foundations

- **Branch:** `redesign/minimal-ui-p1-foundations`
- **Commit:** `feat(ui): establish minimal design foundations`
- **Files touched:** `frontend/src/styles/index.css`; `frontend/src/main.tsx` only if removing unused Plus Jakarta imports.
- **Tasks:**
  1. Replace visual token definitions with Section 3.2, retaining temporary aliases for all old variables.
  2. Remove global radial backgrounds, glass/backdrop filters, gradients, neon glow shadows, custom opaque scrollbar treatment where it reduces contrast, and motion that is purely decorative.
  3. Implement body/page canvas, content max width/gutters, type scale, shared button/chip/badge primitives, surfaces, two-colour focus treatment, and revised reduced-motion block.
  4. Restyle every existing class name in Section 7.3 rather than renaming it. Do not change JSX/state in this phase.
  5. Confirm all existing IDs and test selectors still exist through `rg` and test suite.
- **Acceptance criteria:** the page is visibly neutral/minimal without a broken layout; all production classes/IDs remain; typecheck/lint/tests/build pass; generated static output is rebuilt and staged with source.

### Phase 2 — Reframe entry, status, and lifecycle states

- **Branch:** `redesign/minimal-ui-p2-entry-states`
- **Commit:** `feat(ui): refine analysis entry and progress states`
- **Files touched:** `frontend/src/components/Header.tsx`, `SearchBar.tsx`, `LoadingStepper.tsx`, `SessionWindowBanner.tsx`, `App.tsx`, `frontend/src/styles/index.css`; tests only for added accessible semantics.
- **Tasks:**
  1. Apply Section 5.1–5.4 layout/classes while preserving exact copy, IDs, effects, handlers, and callback argument values.
  2. Add persistent ticker label, run-options grouping, meaningful progressbar/live semantics, and presentation-only clock accessibility treatment.
  3. Convert inline error/empty presentation styles into named CSS classes without changing their conditions/content.
  4. Implement responsive header/input/stepper/session layouts and verify 320–768 px widths.
- **Acceptance criteria:** submit, each quick chip, force refresh, LLM filter toggle, loading sequence, initial error, and session timing display behave identically to baseline; all hooks in Section 7.2 remain exact; keyboard focus/labels are visible and valid.

### Phase 3 — Make signal and trust context unmistakable

- **Branch:** `redesign/minimal-ui-p3-signal-hero`
- **Commit:** `feat(ui): redesign signal hero and trust context`
- **Files touched:** `frontend/src/components/DecisionHero.tsx`, `frontend/src/styles/index.css`, `frontend/src/components/DecisionHero.test.tsx` only to add semantic tests.
- **Tasks:**
  1. Implement Section 5.5’s flat signal hero and four-cell metric layout using the existing classes/IDs.
  2. Move presentation-only inline styles into class rules; retain outcome condition branches verbatim.
  3. Restyle warnings and the heuristic/research footnote so the disclaimer is conspicuous at every breakpoint.
  4. Verify BUY, HOLD (every listed hold reason), SELL, cached, no fresh/relevant news, and degraded data states against fixtures.
- **Acceptance criteria:** all `DecisionHero` value and branch tests pass unchanged; screen has a uniquely clear primary verdict; disclaimer is visible without an interaction; no colours/score values/wording are lost.

### Phase 4 — Organise rationale and evidence for scanning

- **Branch:** `redesign/minimal-ui-p4-evidence`
- **Commit:** `feat(ui): clarify rationale and evidence hierarchy`
- **Files touched:** `RationaleSection.tsx`, `EvidenceExplorer.tsx`, `TelemetryDrawer.tsx`, `HistorySidebar.tsx`, `frontend/src/styles/index.css`; targeted component tests if created.
- **Tasks:**
  1. Apply Sections 5.6–5.9. Use classes in place of visual inline styles and preserve component data calculations/conditions.
  2. Apply filter/disclosure semantics without replacing native buttons or changing local state names/values.
  3. Build compact article rows and semantic probability indicator; choose the safe “details always visible but lower weight” fallback if progressive per-row disclosure risks a functional hook change.
  4. Retain excluded evidence grouping/expansion, all telemetry cells, and history selection controls exactly.
  5. Verify long headlines, missing canonical URL, undated article, no lead text, both effective/final weight fallback, no matching filter, facts empty, no LLM summary, and no history.
- **Acceptance criteria:** exact retained/excluded/filter counts and item content match baseline fixture output; every link and history item remains operable by mouse/keyboard; no hidden evidence is irretrievable; layout works one-column at 375 px.

### Phase 5 — Accessibility and responsive hardening

- **Branch:** `redesign/minimal-ui-p5-a11y-responsive`
- **Commit:** `fix(ui): harden responsive and accessible interaction`
- **Files touched:** `frontend/src/styles/index.css` and only frontend components needing nonfunctional semantic attributes; tests as needed.
- **Tasks:**
  1. Audit every foreground/background pairing and update tokens/styles to WCAG AA targets.
  2. Keyboard-walk every focusable item through header, form, chips, checkboxes, loading state, filters, article links, excluded disclosure, history toggle/items; inspect no focus target hides beneath sticky header.
  3. Test `prefers-reduced-motion`, 200% zoom, 320 px width, touch targets, and forced-colours/high-contrast fallback where available.
  4. Confirm only analysis status is live-announced and semantic status/badges do not rely on colour.
- **Acceptance criteria:** zero horizontal overflow at stated breakpoints; visible focus throughout; valid labels/ARIA relationships; no regressions to existing states, IDs, or class hooks.

### Phase 6 — Automated visual regression and release candidate

- **Branch:** `redesign/minimal-ui-p6-visual-qa`
- **Commit:** `test(ui): add visual regression coverage`
- **Files touched:** `frontend/package.json`, `frontend/package-lock.json`, new `frontend/playwright.config.ts`, new `frontend/tests/visual/**`, optional CI workflow addition only if the team wants CI screenshots; `app/static/**` after final build.
- **Tasks:**
  1. Add Playwright Test dev-only following Section 8; pin a compatible version in lockfile.
  2. Build screenshot stories/mocked API flows for Section 12’s state matrix, rather than changing component logic to manufacture visual states.
  3. Capture and review approved baselines at each required viewport. Use screenshot diffs as a review aid, not a reason to bless text/data changes.
  4. Run complete CI-equivalent commands; rebuild `app/static` from a clean `npm ci` and verify `git diff --exit-code ../app/static` after a second build.
  5. Update release-review notes with known intentional visual diffs and Section 1.1 reference-translation/non-copy conformance.
- **Acceptance criteria:** source and generated bundle are deterministic; screenshot set covers all critical states/viewports; CI-equivalent checks pass; final PR targets only `redesign/minimal-ui` until user authorises review to `main`.

## 12. Verification and regression plan

### 12.1 Required commands

Run from repository root unless noted:

```powershell
git diff --check
cd frontend
npm ci
npm run gen:api
git diff --exit-code src/api/schema.d.ts
npm run typecheck
npm run lint
npm test
npm run build
git diff --exit-code ../app/static
```

Then run the documented backend test suite only as a read-only regression confidence check; do not edit backend tests/configuration to support a CSS change:

```powershell
cd ..
pytest
```

### 12.2 Functional parity checklist

- [ ] Initial health call still occurs once on mount; a health failure remains non-blocking.
- [ ] Ticker input uppercases, keeps `maxLength=16`, and submits only when nonblank/not loading.
- [ ] Each six quick chip submits exactly its current ticker value and retains its ID.
- [ ] Force Refresh and Nemotron 3 Catalyst Filter values/defaults/disabled behaviour are unchanged and passed unchanged to `startAnalysis`.
- [ ] Cache hit presents result immediately and refreshes history exactly as before.
- [ ] SSE progress renders the same stage/message/percentage, completes, errors, and stops/ignores stale jobs exactly as before.
- [ ] Selecting a recent run cancels/ignores the active request as before and displays the selected result.
- [ ] All `AnalysisResult` values and labels render unchanged in session, hero, rationale, evidence, telemetry, and history.
- [ ] BUY/HOLD/SELL plus every HOLD reason, corroboration state, cache state, no-fresh-news, no-relevant-news, and degraded state still render correct exact copy.
- [ ] Evidence filter counts/results, excluded grouping/counts, expand/collapse, external URLs/rel attributes, and article data fallbacks are identical.
- [ ] Telemetry’s five cells and history’s fetch/open/select behaviour are unchanged.
- [ ] Every Section 7 ID, relationship, and class selector is present after a production build.

### 12.3 Screenshot/state matrix

Capture and approve these at **1440×900, 1024×768, 768×1024, and 375×812**:

| State | Required visible proof |
|---|---|
| Empty/default | Legal notice, masthead, labelled ticker input, quick chips/options, intro state. |
| Loading | Progress percent/message and all six stages; reduced-motion variant. |
| BUY with corroborated evidence | Ticker, verdict, four metrics, facts/rationale, retained articles. |
| HOLD / no fresh news | Warning, `n/a` confidence, research disclaimer, no false directional emphasis. |
| SELL / degraded ingestion | Red semantic warning and retained evidence/telemetry context. |
| Filters | All four filter selections and their zero-result message. |
| Excluded evidence | Disclosure expanded with at least two reason groups. |
| History | Collapsed and expanded history with historical-result selection. |
| Error | Existing analysis-error message in its final surface. |
| Long/edge content | Long ticker/company/headline, missing URL, undated article, no facts, no LLM summary. |

### 12.4 Manual accessibility review

- Keyboard only: Tab/Shift+Tab, Enter/Space every control; record focus order.
- Screen reader smoke test: form label, loading announcement, warning/error, filter selected state, excluded/history expanded state, article links, and disclaimer.
- Contrast check: every token pairing used by text, borders that convey states, badge labels, progressbar, focus outline, and disabled text.
- Zoom/reflow: 200% desktop and mobile; inspect 320 px/375 px width without lost content or horizontal page scroll.
- Motion: OS/browser reduced motion active; ensure no spinning/fade movement remains except effectively instantaneous state update.

## 13. Risks and rollback strategy

| Risk | Prevention | Rollback |
|---|---|---|
| A visual refactor accidentally changes a selector test relies on | Preserve all Section 7 IDs/classes; run tests after each phase; do not “fix” tests by changing selectors. | Revert the individual feature-branch commit or PR from `redesign/minimal-ui`; do not reset shared branches. |
| Inline-style migration changes conditional output | Move one component at a time and test every data/status branch against existing fixtures. | Revert that component’s commit, preserving unrelated foundation work. |
| New disclosure hides important evidence or breaks keyboard flow | Default to always-visible lower-weight data if local disclosure cannot be isolated safely. | Remove only the disclosure wrapper/styles, leaving original article content mounted. |
| Minimal palette reduces readability | Use measurable token contrast and text/icon/sign redundancy, not low-opacity aesthetic choices. | Restore a passing token contrast pair; do not revive glows/gradients as a substitute. |
| Responsive changes create overflow | Screenshot and manual test at 320/375/768/1024 px each phase. | Revert the responsive override responsible; retain base desktop system. |
| Build output drift | Rebuild from clean `npm ci`; CI checks `app/static` parity. | Regenerate using `npm run build`; never edit output manually. |
| Reference direction is over-applied or copied too literally | Apply only the translations/non-copy rules in Section 1.1; keep the app’s data density, semantic palette, and accessibility requirements primary. | Revert the isolated visual treatment; retain the tested information architecture and functional hooks. |

**Rollback commands (executed only after deciding which reviewed commit to reverse):** use `git revert <commit>` on the feature/integration branch, push the revert branch, and review it through the same manual PR process. Never use `git reset --hard`, force-push, or a direct main-branch rollback for this work.

## 14. Final owner review checklist

- [ ] The product reads as a restrained research tool, not a neon trading dashboard.
- [ ] The legal and result research/not-financial-advice notices are immediately visible and unchanged in meaning.
- [ ] The primary scan order is ticker → classification → confidence/evidence quality → explanation → source evidence.
- [ ] All existing controls, data fields, empty/error/degraded states, telemetry, history, and exclusions still exist and work.
- [ ] BUY/HOLD/SELL remains explicit text + icon/sign + colour; no recommendation is implied more strongly by visual treatment than the current algorithm/data supports.
- [ ] Desktop, tablet, and mobile screenshots satisfy the matrix; no clipped/overflowing content or obscured focus appears.
- [ ] Keyboard, reduced-motion, contrast, and screen-reader smoke tests pass.
- [ ] No API/data/state/scoring/backend file changed; `git diff` confirms this.
- [ ] All preserved IDs/classes and test selectors are still present.
- [ ] `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`, static-bundle parity, and backend regression suite pass.
- [ ] ZEGGO informed restraint, hierarchy, whitespace, and paced polish only; no logo, palette, imagery, 3D, copy, or interaction sequence was copied.
- [ ] Each phase was reviewed through a PR into `redesign/minimal-ui`; only an explicit owner-approved final PR may be manually merged to `main`.

