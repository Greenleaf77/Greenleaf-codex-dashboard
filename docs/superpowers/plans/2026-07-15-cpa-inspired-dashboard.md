# CPA-Inspired Dashboard Visual Redesign Implementation Plan

> **For agentic workers:** Execute this plan inline in the current session. Do
> not use subagents, SDD, or commits unless the user explicitly requests them.
> Track progress with checkbox (`- [ ]`) syntax.

**Goal:** Restyle Codex Usage Dashboard as a warm graphite telemetry console
while preserving all existing usage, chart, table, filter, and Diagnostics
behavior.

**Architecture:** Keep the Python API and frontend data flow unchanged. Extract
compact-number formatting into a small testable ES module, then reshape only
the HTML produced by `src/main.js` and replace the presentation system in
`src/styles.css`. Sparklines are rendered as inline SVG from the existing
`daily` payload, so no backend fields or dependencies are added.

**Tech Stack:** Python 3.10 standard library, SQLite, JSONL, vanilla
JavaScript ES modules, inline SVG, CSS, Vite 8, Node.js 20 built-in test runner.

## Global Constraints

- Keep the dashboard dark-only; do not add a theme switcher.
- Preserve every current metric, filter, visualization, table column,
  expandable model row, and lazy Diagnostics behavior.
- Do not change API payloads, token accounting, pricing, or persisted state.
- Do not add React, chart libraries, fonts, icon packages, or other
  dependencies.
- Implement the visual system from scratch; do not bundle reference-project
  code or assets and do not add project credit.
- Use `B` with one decimal at or above `1,000,000,000` in compact contexts.
- Keep full localized integers in Usage, Models, and Diagnostics table cells.
- Run only the focused formatter test, existing telemetry unit test, existing
  smoke check, Vite build, and targeted browser smoke.
- Preserve the unrelated untracked 2026-06-28 plan and spec files.
- The final README screenshot must show the main Usage view and the complete
  top metric area; Diagnostics must not be active.

---

### Task 1: Add testable billion-scale compact formatting

**Files:**

- Create: `src/format.js`
- Create: `tests/compact-format.test.mjs`
- Modify: `src/main.js:1-85`

**Interfaces:**

- Produces: `compactNumber(value: unknown) -> string`
- Consumed by: metric cards, chart-axis labels, peak-day notes, and
  Diagnostics summaries in `src/main.js`
- Preserves: the existing `full()` and `money()` formatting behavior

- [ ] **Step 1: Add the focused formatter test first**

```js
// tests/compact-format.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { compactNumber } from "../src/format.js";

test("compactNumber switches from millions to billions at one billion", () => {
  assert.equal(compactNumber(999), "999");
  assert.equal(compactNumber(1_000), "1.0k");
  assert.equal(compactNumber(999_000_000), "999.0M");
  assert.equal(compactNumber(1_000_000_000), "1.0B");
  assert.equal(compactNumber(4_592_343_722), "4.6B");
});

test("compactNumber normalizes missing values to zero", () => {
  assert.equal(compactNumber(undefined), "0");
  assert.equal(compactNumber(null), "0");
});
```

- [ ] **Step 2: Run the test and confirm it fails because the module is absent**

Run:

```bash
node --test tests/compact-format.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `src/format.js`.

- [ ] **Step 3: Create the formatter module**

```js
// src/format.js
const numberFormatter = new Intl.NumberFormat("en-US");

export function compactNumber(value) {
  const number = Number(value || 0);
  if (number >= 1_000_000_000) return `${(number / 1_000_000_000).toFixed(1)}B`;
  if (number >= 1_000_000) return `${(number / 1_000_000).toFixed(1)}M`;
  if (number >= 1_000) return `${(number / 1_000).toFixed(1)}k`;
  return numberFormatter.format(number);
}
```

- [ ] **Step 4: Replace the local helper in `src/main.js`**

Add the import next to the stylesheet import:

```js
import "./styles.css";
import { compactNumber } from "./format.js";
```

Remove the current `compact()` function and replace all eight call sites:

```js
compactNumber(tick)
compactNumber(summary.estimated_local_overcount_tokens)
compactNumber(totals.input_tokens)
compactNumber(totals.output_tokens)
compactNumber(totals.total_tokens)
compactNumber(totals.cached_input_tokens)
compactNumber(totals.total_with_cached_tokens)
compactNumber(data.peak_day_tokens)
```

Do not replace `full()` calls in table markup.

- [ ] **Step 5: Run the focused test and frontend build**

Run:

```bash
node --test tests/compact-format.test.mjs
npm run build
```

Expected: two formatter tests pass; Vite exits with code 0.

- [ ] **Step 6: Inline self-review**

Check that every removed `compact()` call now uses `compactNumber()`, while
all Daily Usage, Models, model-detail, and Diagnostics row cells still use
`full()`.

---

### Task 2: Build the framed header, metric hierarchy, and sparklines

**Files:**

- Modify: `src/main.js:678-737`
- Modify: `src/main.js:822-829`

**Interfaces:**

- Produces:
  - `dailySeries(data, key) -> number[]`
  - `renderSparkline(values, label) -> string`
  - `metricCard(options) -> string`
- Consumes: existing `data.daily`, `data.totals`, pricing metadata, icon
  markup, and escaped display strings
- Preserves: all existing `data-range`, `data-visualization`,
  `data-chart-range`, form IDs, and checkbox IDs used by event binding

- [ ] **Step 1: Add pure daily-series and sparkline helpers**

Add these helpers above `render()`:

```js
function dailySeries(data, key) {
  return (data.daily || []).map((row) => Number(row[key] || 0));
}

function renderSparkline(values, label) {
  const series = values.filter((value) => Number.isFinite(value));
  if (series.length < 2 || !series.some((value) => value > 0)) return "";
  const width = 320;
  const height = 58;
  const inset = 4;
  const max = Math.max(...series, 1);
  const step = (width - inset * 2) / Math.max(series.length - 1, 1);
  const points = series.map((value, index) => {
    const x = inset + index * step;
    const y = height - inset - (value / max) * (height - inset * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const area = `${inset},${height - inset} ${points} ${width - inset},${height - inset}`;
  return `
    <div class="metric-sparkline" role="img" aria-label="${escapeHtml(label)}">
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
        <polygon points="${area}"></polygon>
        <polyline points="${points}"></polyline>
      </svg>
    </div>
  `;
}
```

- [ ] **Step 2: Replace `card()` with an option-based metric renderer**

```js
function metricCard({
  label,
  value,
  iconName,
  tone,
  note = "",
  series = [],
  hero = false
}) {
  const classes = ["metric-card", `metric-${tone}`, hero ? "metric-card-hero" : ""]
    .filter(Boolean)
    .join(" ");
  return `
    <article class="${classes}">
      <span class="metric-accent" aria-hidden="true"></span>
      <div class="metric-card-head">
        <div class="metric-label">${escapeHtml(label)}</div>
        <span class="metric-icon">${icon(iconName)}</span>
      </div>
      <div class="metric-value">${value}</div>
      ${note ? `<div class="metric-note">${note}</div>` : ""}
      ${renderSparkline(series, `${label} trend`)}
    </article>
  `;
}
```

Values and notes that already contain trusted local markup must be assembled
at the call site; all source strings inside them must remain escaped.

- [ ] **Step 3: Reshape the header without changing control hooks**

Use this exact rounded `header.app-header` template:

```js
<header class="app-header">
  <div class="brand-block">
    <div class="brand-pill">
      <span class="brand-mark">${icon("brand")}</span>
      <h1>Codex Usage</h1>
    </div>
    <div class="brand-meta">
      <span>Generated ${escapeHtml(data.generated_at)} from local Codex logs</span>
      <strong>Showing ${escapeHtml(describeRange(data))}</strong>
    </div>
  </div>
  <div class="header-tools">
    <label class="toggle-option">
      <input id="ignore-auto-review" type="checkbox" ${data.ignore_auto_review ? "checked" : ""}>
      <span>Ignore "${escapeHtml(autoReviewModel)}" model</span>
    </label>
    <nav class="segments" aria-label="Range">
      ${rangeOptions.map((range) => `<button class="seg ${data.range === range.value ? "active" : ""}" data-range="${range.value}">${range.label}</button>`).join("")}
    </nav>
    ${data.range === "custom" ? `
      <form class="custom-range" id="custom-range-form">
        <label>
          <span>From</span>
          <input id="custom-start" type="date" value="${escapeHtml(data.range_start || customStartDate)}">
        </label>
        <label>
          <span>To</span>
          <input id="custom-end" type="date" value="${escapeHtml(data.range_end || customEndDate)}">
        </label>
        <button class="custom-apply" type="submit">Apply</button>
      </form>
    ` : ""}
  </div>
</header>
```

Do not add theme, language, update, authentication, or navigation controls.

- [ ] **Step 4: Render two hero metrics and all remaining metrics**

Replace `.cards` with:

```js
<div class="metric-stage">
  <div class="hero-metrics">
    ${metricCard({
      label: "Total tokens",
      value: compactNumber(totals.total_with_cached_tokens),
      iconName: "layers",
      tone: "violet",
      note: `Cached ${compactNumber(totals.cached_input_tokens)} · Without cache ${compactNumber(totals.total_tokens)}`,
      series: dailySeries(data, "total_with_cached_tokens"),
      hero: true
    })}
    ${metricCard({
      label: "API estimate",
      value: money(totals.cost_usd),
      iconName: "coin",
      tone: "amber",
      note: escapeHtml(data.pricing?.source || "pricing unavailable"),
      series: dailySeries(data, "cost_usd"),
      hero: true
    })}
  </div>
  <div class="secondary-metrics">
    ${metricCard({
      label: "Sessions",
      value: full(totals.sessions),
      iconName: "sessions",
      tone: "blue",
      series: dailySeries(data, "sessions")
    })}
    ${metricCard({
      label: "Input tokens",
      value: compactNumber(totals.input_tokens),
      iconName: "input",
      tone: "blue",
      series: dailySeries(data, "input_tokens")
    })}
    ${metricCard({
      label: "Output tokens",
      value: compactNumber(totals.output_tokens),
      iconName: "output",
      tone: "green",
      series: dailySeries(data, "output_tokens")
    })}
    ${metricCard({
      label: "Total w/o cached",
      value: compactNumber(totals.total_tokens),
      iconName: "calculator",
      tone: "coral",
      series: dailySeries(data, "total_tokens")
    })}
    ${metricCard({
      label: "Cached input",
      value: compactNumber(totals.cached_input_tokens),
      iconName: "cache",
      tone: "cyan",
      series: dailySeries(data, "cached_input_tokens")
    })}
    ${metricCard({
      label: "Active days",
      value: full(totals.active_days),
      iconName: "calendar",
      tone: "blue"
    })}
    ${metricCard({
      label: "Favorite model",
      value: escapeHtml(data.favorite_model),
      iconName: "star",
      tone: "violet"
    })}
    ${metricCard({
      label: "Current streak",
      value: `${full(data.current_streak)}d`,
      iconName: "flame",
      tone: "coral"
    })}
    ${metricCard({
      label: "Longest streak",
      value: `${full(data.longest_streak)}d`,
      iconName: "trophy",
      tone: "amber"
    })}
    ${metricCard({
      label: "Peak day",
      value: escapeHtml(data.peak_day),
      iconName: "chart",
      tone: "green",
      note: data.peak_day_tokens ? compactNumber(data.peak_day_tokens) : "",
      series: dailySeries(data, "total_tokens")
    })}
    ${metricCard({
      label: "Data source",
      value: "SQLite + JSONL",
      iconName: "database",
      tone: "violet"
    })}
  </div>
</div>
```

Do not add series to Active days, Favorite model, streaks, or Data source.

- [ ] **Step 5: Retune the existing model chart palette**

Replace `chartColors` without changing `modelColor()`:

```js
const chartColors = [
  "#3b82f6",
  "#22c55e",
  "#f59e0b",
  "#8b5cf6",
  "#14b8a6",
  "#f05d4f",
  "#60a5fa",
  "#a3e635"
];
```

- [ ] **Step 6: Build and inspect the DOM contract**

Run:

```bash
npm run build
```

Expected: Vite exits with code 0.

Then inspect the rendered DOM and confirm:

- exactly two `.metric-card-hero` elements;
- all 13 original metrics remain present;
- the ignore-auto-review checkbox and all range buttons are still bindable;
- no unescaped model, pricing-source, date, or error string was introduced.

- [ ] **Step 7: Inline self-review**

Review only the `src/main.js` diff for unrelated behavior changes. Confirm
fetching, URL state, lazy Diagnostics, range changes, chart changes, and model
expansion functions are byte-for-byte unchanged outside presentation call
sites.

---

### Task 3: Apply the warm graphite component system

**Files:**

- Modify: `src/styles.css`

**Interfaces:**

- Consumes: the class names introduced in Task 2 and all existing
  visualization/table/Diagnostics class names
- Produces: one dark-only token system, responsive card layouts, pill
  controls, inset chart/table surfaces, and accessible states

Before editing, use this design checkpoint:

```text
Intent: a developer checks local token scale, cost, model mix, and telemetry anomalies.
Palette: soot canvas, warm graphite panels, chalk text, semantic instrument lights.
Depth: surface shifts and quiet borders; shadows only for header, active pills, and metric cards.
Surfaces: canvas #151412, panel #1d1b18, raised #262320, inset #11100e.
Typography: SF Pro/Segoe UI system stack; tabular numeric data; tight bold headings.
Spacing: 4px base unit.
```

- [ ] **Step 1: Replace the root tokens and page frame**

```css
:root {
  color-scheme: dark;
  --void: #0d0c0b;
  --soot: #151412;
  --graphite: #1d1b18;
  --graphite-raised: #262320;
  --graphite-inset: #11100e;
  --chalk: #f6f4f1;
  --ash-light: #c9c3bb;
  --ash: #9c958d;
  --ash-dark: #6f6962;
  --line-soft: rgba(201, 195, 187, 0.10);
  --line: rgba(201, 195, 187, 0.16);
  --line-strong: rgba(201, 195, 187, 0.24);
  --blue: #3b82f6;
  --cyan: #14b8a6;
  --green: #22c55e;
  --violet: #8b5cf6;
  --amber: #f59e0b;
  --coral: #f05d4f;
  --heat-0: #262320;
  --heat-1: #203228;
  --heat-2: #1d5a32;
  --heat-3: #1e8a43;
  --heat-4: #22c55e;
  --shadow-header: 0 16px 36px rgba(0, 0, 0, 0.18);
  --shadow-panel: 0 12px 28px rgba(0, 0, 0, 0.16);
  --shadow-control: 0 5px 14px rgba(0, 0, 0, 0.24);
  --shadow-tooltip: 0 16px 32px rgba(0, 0, 0, 0.38);
  --canvas: var(--soot);
  --surface-1: var(--graphite);
  --surface-2: var(--graphite-raised);
  --surface-inset: var(--graphite-inset);
  --border-soft: var(--line-soft);
  --border: var(--line);
  --border-strong: var(--line-strong);
  --text-primary: var(--chalk);
  --text-secondary: var(--ash-light);
  --text-tertiary: var(--ash);
  --text-muted: var(--ash-dark);
  --lime: var(--green);
}

body {
  background: var(--void);
  color: var(--chalk);
  font-family: "SF Pro Text", "SF Pro Display", "Segoe UI", system-ui, sans-serif;
}

#app {
  width: min(1680px, calc(100vw - 40px));
  margin: 28px auto 56px;
  padding: 20px;
  border: 1px solid var(--line-soft);
  border-radius: 28px;
  background: var(--soot);
}
```

- [ ] **Step 2: Style the framed header and pill controls**

Replace the existing header, brand, and control rules with:

```css
.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 20px;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: color-mix(in srgb, var(--graphite) 92%, var(--void));
  box-shadow: var(--shadow-header);
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 16px;
  min-width: 0;
}

.brand-pill {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 7px 18px 7px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--chalk);
  font-size: 14px;
  font-weight: 760;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  white-space: nowrap;
}

.brand-pill h1 {
  margin: 0;
  color: inherit;
  font: inherit;
}

.brand-meta {
  display: grid;
  gap: 3px;
  color: var(--ash);
  font-size: 12px;
}

.brand-meta strong {
  color: var(--green);
  font-weight: 650;
}

.header-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.segments,
.toggle-option {
  min-height: 44px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--graphite-inset);
}

.segments {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 4px;
}

.seg {
  min-height: 34px;
  padding: 7px 13px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ash);
  cursor: pointer;
  font-size: 12px;
  font-weight: 680;
}

.seg:hover { color: var(--chalk); }

.seg.active {
  color: var(--chalk);
  background: var(--graphite-raised);
  box-shadow: var(--shadow-control);
}

.toggle-option {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 8px 14px;
  color: var(--ash-light);
  cursor: pointer;
  font-size: 12px;
}

.custom-range {
  display: flex;
  align-items: end;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--graphite-inset);
}

.custom-range input,
.custom-apply {
  min-height: 36px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--soot);
  color: var(--chalk);
}

:where(button, input):focus-visible {
  outline: 2px solid color-mix(in srgb, var(--blue) 78%, var(--chalk));
  outline-offset: 2px;
}
```

- [ ] **Step 3: Style the hero and secondary metric grids**

```css
.hero-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.secondary-metrics {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.metric-card {
  --metric-accent: var(--blue);
  position: relative;
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 18px;
  background:
    radial-gradient(circle at 12% 0%, color-mix(in srgb, var(--metric-accent) 16%, transparent), transparent 48%),
    var(--graphite);
  box-shadow: var(--shadow-panel);
  display: flex;
  flex-direction: column;
  min-height: 148px;
  padding: 20px;
}

.metric-card-hero {
  min-height: 214px;
  padding: 28px;
}

.metric-accent {
  position: absolute;
  inset: 0 0 auto;
  height: 4px;
  background: linear-gradient(90deg, var(--metric-accent), transparent 72%);
}

.metric-sparkline {
  height: 64px;
  margin-top: auto;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: color-mix(in srgb, var(--graphite-inset) 88%, transparent);
}

.metric-sparkline svg {
  display: block;
  width: 100%;
  height: 100%;
}

.metric-sparkline polygon {
  fill: color-mix(in srgb, var(--metric-accent) 22%, transparent);
}

.metric-sparkline polyline {
  fill: none;
  stroke: var(--metric-accent);
  stroke-width: 2.4;
  vector-effect: non-scaling-stroke;
}

.metric-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.metric-label {
  color: var(--ash);
  font-size: 12px;
  font-weight: 680;
}

.metric-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border: 1px solid color-mix(in srgb, var(--metric-accent) 36%, transparent);
  border-radius: 12px;
  color: var(--chalk);
  background: var(--metric-accent);
  box-shadow: 0 10px 24px color-mix(in srgb, var(--metric-accent) 18%, transparent);
}

.metric-value {
  margin: 18px 0 4px;
  color: var(--chalk);
  font-size: clamp(24px, 2vw, 36px);
  font-weight: 780;
  letter-spacing: -0.035em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.metric-card-hero .metric-value {
  font-size: clamp(36px, 4vw, 56px);
}

.metric-note {
  color: var(--ash);
  font-size: 12px;
}
```

Assign tones explicitly:

```css
.metric-blue { --metric-accent: var(--blue); }
.metric-cyan { --metric-accent: var(--cyan); }
.metric-green { --metric-accent: var(--green); }
.metric-violet { --metric-accent: var(--violet); }
.metric-amber { --metric-accent: var(--amber); }
.metric-coral { --metric-accent: var(--coral); }
```

Delete every obsolete `.cards` media rule and the old `.card`,
`.metric-copy`, `.label`, `.value`, `.metric-lime`, `.metric-slate`,
`.subtle`, `.segment-note`, and circular `.metric-icon` rules so they
cannot override the new metric system. Replace the old combined
`.card, section` block with the standalone `section` block in Step 4.

- [ ] **Step 4: Restyle visualization and table workspaces**

Use these base rules, then map the existing component selectors to them:

```css
section {
  min-width: 0;
  margin-top: 18px;
  padding: 22px 24px;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: var(--graphite);
}

.heat-wrap,
.chart-shell {
  margin-top: 18px;
  padding: 18px;
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: var(--graphite-inset);
}

.chart-grid span,
.chart-v-grid span,
th,
td {
  border-color: var(--line-soft);
}

.heat-tooltip {
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  background: var(--graphite-raised);
  box-shadow: var(--shadow-tooltip);
}

.tables {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.08fr);
  gap: 18px;
  align-items: start;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

th {
  color: var(--ash);
  background: color-mix(in srgb, var(--graphite-inset) 72%, transparent);
  font-size: 11px;
  font-weight: 700;
}

tbody tr:hover > td {
  background: color-mix(in srgb, var(--graphite-raised) 56%, transparent);
}

tfoot td {
  color: var(--green);
  font-weight: 760;
}

.detail-card,
.diagnostics-summary > div {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  background: var(--graphite-inset);
}

.diagnostics-state,
.state {
  border: 1px solid var(--line);
  border-radius: 22px;
  background: var(--graphite);
}
```

Preserve the current chart heights, heat-cell data attributes, tooltip data
attributes, table minimum widths, Diagnostics grid columns, expanded-row
markup, and loading/retry selectors. Replace their color, background, border,
radius, and shadow values with the root tokens rather than changing layout or
behavior.

- [ ] **Step 5: Add responsive rules**

```css
@media (max-width: 1180px) {
  .secondary-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

@media (max-width: 820px) {
  .app-header,
  .viz-header { flex-direction: column; }
  .hero-metrics { grid-template-columns: 1fr; }
  .secondary-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tables { grid-template-columns: 1fr; }
}

@media (max-width: 520px) {
  #app { width: calc(100vw - 16px); padding: 12px; border-radius: 20px; }
  .secondary-metrics { grid-template-columns: 1fr; }
}
```

Retain `prefers-reduced-motion: reduce` and horizontal table scrolling.

- [ ] **Step 6: Run the build and CSS scope review**

Run:

```bash
npm run build
git diff --check -- src/main.js src/styles.css src/format.js tests/compact-format.test.mjs
```

Expected: both commands exit with code 0.

Review the CSS for random literal colors outside `:root`, mixed radius
systems, missing focus/hover states, harsh borders, and selectors that no
longer match rendered markup.

---

### Task 4: Browser-smoke behavior and responsive layouts

**Files:**

- Verify only: `src/main.js`, `src/styles.css`

**Interfaces:**

- Uses the local Vite/Python dashboard at `http://127.0.0.1:8765/`
- Must not change local SQLite or rollout data

- [ ] **Step 1: Start the local dashboard**

Run:

```bash
npm run dev:all
```

Expected: Vite listens on `127.0.0.1:8765` and the API listens on
`127.0.0.1:8766`.

- [ ] **Step 2: Smoke the desktop Usage view**

Using the in-app browser:

- load the default Usage view;
- confirm the complete header, both hero cards, all secondary metric cards,
  visualization panel, Usage/Diagnostics pills, Daily Usage, and Models;
- confirm billion-scale cards show values such as `4.6B`;
- confirm table cells continue to show full localized integers;
- inspect the browser console and require zero uncaught errors.

- [ ] **Step 3: Smoke existing interactions**

Exercise:

- main ranges: All, 30d, 7d, 1d;
- main custom date range;
- Daily heatmap and Tokens over time;
- one chart range and chart custom dates;
- ignore-auto-review checkbox;
- one model expansion and collapse;
- Diagnostics lazy load and return to Usage.

Expected: the same values and URL state transitions as before the redesign,
with no clipped controls or stale workspace.

- [ ] **Step 4: Inspect narrow layouts**

Inspect tablet and mobile-sized browser views. Confirm:

- hero cards stack;
- secondary metrics become two columns and then one;
- header controls wrap instead of overflowing;
- chart controls remain reachable;
- tables scroll horizontally;
- Diagnostics summaries stack cleanly;
- 44px mobile control targets and keyboard focus remain visible.

- [ ] **Step 5: Run the visual craft checks**

- Squint: hierarchy remains clear without borders becoming dominant.
- Signature: top accent, wash, squared icon, value hierarchy, and sparkline
  are visible on at least five metric cards.
- Token: every surface, text, border, and semantic color traces to a root
  custom property.
- Swap: the result no longer resembles the previous generic five-column card
  grid.

---

### Task 5: Update documentation, screenshot, and final validation

**Files:**

- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/screenshot.png`
- Review: `docs/superpowers/specs/2026-07-15-cpa-inspired-dashboard-design.md`
- Review: `docs/superpowers/plans/2026-07-15-cpa-inspired-dashboard.md`

**Interfaces:**

- README image path remains `docs/screenshot.png`
- Screenshot shows real local aggregated data but no prompts, thread titles,
  working directories, or message content

- [ ] **Step 1: Update user-facing documentation**

Add these exact README Feature bullets:

```markdown
- Warm graphite telemetry-console interface with responsive hero metrics and compact daily sparklines
- Billion-scale compact values in cards and charts while detailed tables preserve full token counts
```

Do not add a credit, attribution section, or reference-project link.

Insert this changelog section immediately below `# Changelog`:

```markdown
## Unreleased

- Redesigned the dark dashboard as a warm graphite telemetry console with pill controls and layered panels.
- Added responsive hero and secondary metric cards with daily sparklines derived from existing usage data.
- Added billion-scale compact formatting for cards and chart labels while preserving full values in tables.
```

Do not assign a release version unless the user requests one.

- [ ] **Step 2: Capture the README screenshot**

Return to this exact state:

```text
/?range=30d&visualization=heatmap&chart_range=30d
Table workspace: Usage
Ignore codex-auto-review: checked
Expanded model rows: none
```

The capture must include:

- framed header;
- both hero cards;
- every secondary metric card;
- at least the top of the visualization or Usage workspace;
- no active Diagnostics view;
- no loading, tooltip, expanded model, or error overlay.

Save a real PNG to `docs/screenshot.png` and inspect the resulting file with
an image viewer. Use a desktop width of at least 1280px. If the viewport cannot
fit the full metric area, capture the full page and crop only the bottom after
the complete metric area and the top of the visualization are visible; never
crop the framed header or any metric card.

- [ ] **Step 3: Run fresh basic validation**

Run:

```bash
node --test tests/compact-format.test.mjs
python3 -m unittest discover -s tests -v
python3 -m py_compile dashboard_api.py
npm run check
npm run build
git diff --check
```

Expected:

- formatter tests pass;
- all four telemetry tests pass;
- Python compilation exits 0;
- smoke check reports the configured SQLite path passed;
- Vite build exits 0;
- diff check exits 0.

- [ ] **Step 4: Final inline scope and quality review**

Confirm the final diff contains only:

- the approved design spec and implementation plan;
- formatter module and focused test;
- presentation changes in `src/main.js` and `src/styles.css`;
- README, changelog, and screenshot updates.

Confirm `dashboard_api.py`, telemetry accounting, API query behavior, and
unrelated 2026-06-28 documents are unchanged. Do not stage, commit, tag, or
push unless the user explicitly asks.
