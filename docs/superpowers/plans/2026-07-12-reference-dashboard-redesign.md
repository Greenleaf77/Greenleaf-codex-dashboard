# Reference Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the existing Codex usage dashboard to closely match the approved graphite reference and add distinct multicolor SVG icons without changing data or behavior.

**Architecture:** Keep the current single-page rendering architecture. Add one presentation-only SVG helper and icon metadata in `src/main.js`, then replace the existing CSS theme in `src/styles.css` with a coherent tokenized graphite system; no backend, state, request, calculation, or event-handler code changes.

**Tech Stack:** Vanilla JavaScript template rendering, inline SVG, CSS, Vite 8.

## Global Constraints

- Preserve all existing data, copy, metric order, calculations, API requests, URL state, cookies, filters, chart behavior, heatmap behavior, tables, tooltips, and responsive functionality.
- Add no production dependency.
- Do not modify `dashboard_api.py`.
- Keep icons decorative with `aria-hidden="true"`.
- Do not create a git commit unless the user explicitly requests one.

## File Map

- Modify `src/main.js`: presentation-only icon definitions, title mark, section-heading icons, and metric-card wrappers/classes.
- Modify `src/styles.css`: graphite theme tokens, compact layout, component surfaces, icon color variants, controls, charts, tables, focus states, and responsive rules.
- Do not modify `index.html`, API code, package metadata, or application state logic.

---

### Task 1: Add the SVG presentation layer

**Files:**
- Modify: `src/main.js:20-22, 235-253, 415-609`

**Interfaces:**
- Consumes: existing `card(label, value)` calls and render template.
- Produces: `icon(name) -> string` and `card(label, value, iconName, tone) -> string`; neither touches state or data.

- [ ] **Step 1: Record the behavior boundary before editing**

Run:

```bash
git diff -- src/main.js src/styles.css
```

Expected: no pre-existing tracked changes in either target file. If changes exist, preserve and work around them.

- [ ] **Step 2: Add an inline SVG helper with explicit icon paths**

Add a constant object near `chartColors` with one 24×24 path fragment for each approved name (`brand`, `sessions`, `input`, `output`, `calculator`, `cache`, `layers`, `calendar`, `coin`, `star`, `flame`, `trophy`, `chart`, `database`, `usage`, `models`). Add this renderer:

```js
function icon(name, className = "") {
  const paths = iconPaths[name] || iconPaths.layers;
  return `<svg class="icon ${className}" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
}
```

Use only SVG primitives (`path`, `line`, `circle`, `rect`, `polyline`) with no external asset requests.

- [ ] **Step 3: Add presentation wrappers to headings**

Change only template markup so the title and section headings can carry icons:

```js
<div class="brand-block">
  <span class="brand-mark">${icon("brand")}</span>
  <div>
    <h1>Codex Usage</h1>
    ...
  </div>
</div>
```

Use `section-title` wrappers with `usage` and `models` icons for the visualization and table headings. Keep every existing heading string unchanged.

- [ ] **Step 4: Extend metric cards with icon identity**

Pass explicit icon and tone arguments to all thirteen existing cards, preserving their order and values:

```js
${card("Sessions", full(totals.sessions), "sessions", "violet")}
${card("Input tokens", compact(totals.input_tokens), "input", "blue")}
${card("Output tokens", compact(totals.output_tokens), "output", "cyan")}
${card("Total w/o cached", compact(totals.total_tokens), "calculator", "slate")}
${card("Cached input", compact(totals.cached_input_tokens), "cache", "violet")}
${card("Total tokens", compact(totals.total_with_cached_tokens), "layers", "cyan")}
${card("Active days", full(totals.active_days), "calendar", "slate")}
${card("API estimate", value, "coin", "lime")}
${card("Favorite model", escapeHtml(data.favorite_model), "star", "amber")}
${card("Current streak", value, "flame", "coral")}
${card("Longest streak", value, "trophy", "amber")}
${card("Peak day", value, "chart", "blue")}
${card("Data source", "SQLite + JSONL", "database", "violet")}
```

Update the helper to render a two-column visual wrapper:

```js
function card(label, value, iconName, tone) {
  return `<div class="card metric-${tone}"><span class="metric-icon">${icon(iconName)}</span><div class="metric-copy"><div class="label">${label}</div><div class="value">${value}</div></div></div>`;
}
```

- [ ] **Step 5: Verify that only presentation markup changed**

Run:

```bash
git diff --word-diff=plain -- src/main.js
```

Expected: additions are limited to SVG constants/helper, icon arguments, and presentational wrappers/classes; fetch logic, formatters, state variables, event listeners, and chart calculations remain byte-for-byte unchanged.

### Task 2: Apply the graphite design system

**Files:**
- Modify: `src/styles.css:1-500`

**Interfaces:**
- Consumes: `brand-block`, `brand-mark`, `section-title`, `metric-*`, `metric-icon`, and `metric-copy` classes from Task 1.
- Produces: the complete visual presentation; no DOM behavior.

- [ ] **Step 1: Replace primitive color and elevation tokens**

Define the approved palette at `:root` and use tokens everywhere instead of scattered colors:

```css
:root {
  color-scheme: dark;
  --canvas: #0d1016;
  --surface-1: #12161e;
  --surface-2: #171c26;
  --surface-inset: #0f131b;
  --border-soft: rgba(255, 255, 255, 0.055);
  --border: rgba(255, 255, 255, 0.085);
  --border-strong: rgba(255, 255, 255, 0.14);
  --text-primary: #f4f6fb;
  --text-secondary: #c2c8d4;
  --text-tertiary: #8992a3;
  --text-muted: #626b7b;
  --blue: #61a8ff;
  --cyan: #50d5cf;
  --lime: #a6df57;
  --violet: #a58bff;
  --amber: #f4c95d;
  --coral: #f27f6d;
}
```

Map legacy heat tokens to compatible blue values so heatmap behavior is unchanged.

- [ ] **Step 2: Restyle the page frame and header**

Use a neutral system sans-serif stack, a maximum content width matching the current wide dashboard, 4px-based spacing, and compact typography. Style `.brand-mark` as a violet-blue 38px rounded square and keep `.header-tools` right-aligned on desktop.

- [ ] **Step 3: Restyle controls with inset depth and focus visibility**

Apply `--surface-inset` to checkbox rows, segments, date inputs, and custom forms. Active segments use `--surface-2` plus a soft inner/outer highlight. Add:

```css
:where(button, input):focus-visible {
  outline: 2px solid color-mix(in srgb, var(--blue) 78%, white);
  outline-offset: 2px;
}
```

Do not change control dimensions enough to alter wrapping behavior at existing breakpoints.

- [ ] **Step 4: Build compact icon-led metric cards**

Keep the five-column desktop grid and existing responsive collapse. Use a minimum height near 76px, a 12px gap, and this icon pattern:

```css
.metric-icon {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  color: var(--metric-accent);
  background: color-mix(in srgb, var(--metric-accent) 12%, transparent);
  box-shadow: 0 0 20px color-mix(in srgb, var(--metric-accent) 9%, transparent);
}

.metric-blue { --metric-accent: var(--blue); }
.metric-cyan { --metric-accent: var(--cyan); }
.metric-lime { --metric-accent: var(--lime); }
.metric-violet { --metric-accent: var(--violet); }
.metric-amber { --metric-accent: var(--amber); }
.metric-coral { --metric-accent: var(--coral); }
.metric-slate { --metric-accent: #9aa6b9; }
```

Keep labels secondary and values primary with tabular numerals.

- [ ] **Step 5: Unify visualization and table surfaces**

Apply `--surface-1`, the same 8px radius, and quiet `--border-soft` edges to sections. Reduce grid-line contrast, soften table separators, preserve all minimum widths/scrollers, and use the existing model colors for chart identity.

- [ ] **Step 6: Preserve responsive behavior**

At `980px`, retain two card columns and stacked table panels. At `520px`, retain one card column and vertical header/forms. Ensure `.brand-block` and `.section-title` remain aligned and no new fixed width causes page-level overflow.

- [ ] **Step 7: Build the frontend**

Run:

```bash
npm run build
```

Expected: Vite exits with code 0 and writes the production bundle without JavaScript or CSS errors.

### Task 3: Visual and behavioral regression check

**Files:**
- Verify: `src/main.js`
- Verify: `src/styles.css`

**Interfaces:**
- Consumes: completed presentation layer and CSS design system.
- Produces: evidence that the redesign is visual-only and usable at desktop and narrow widths.

- [ ] **Step 1: Start the existing local dashboard**

Run:

```bash
npm start
```

Expected: frontend is available at `http://127.0.0.1:8765/` and the existing data API responds.

- [ ] **Step 2: Compare the desktop render with the reference**

At approximately 1280×720, verify: near-black canvas, compact graphite cards, five-column summary grid, soft boundaries, branded heading mark, distinct colored metric icons, dense visualization panel, and paired table panels.

- [ ] **Step 3: Exercise all existing interactions**

Verify each range control, ignore-model checkbox, visualization tab, chart range, both custom date forms, heatmap/chart tooltip, and model-row expansion works as before. Expected: no console errors and no missing/reformatted data.

- [ ] **Step 4: Check narrow layout and keyboard focus**

At widths near 900px and 390px, verify card grids collapse to two and one column respectively; tables/charts scroll only inside their containers; header controls remain usable; Tab navigation shows a visible focus ring.

- [ ] **Step 5: Run final static checks**

Run:

```bash
npm run build
npm run check
git diff --check
git diff --stat
```

Expected: both npm commands exit 0, `git diff --check` prints nothing, and the stat lists only `src/main.js` and `src/styles.css` as implementation files plus the approved design/plan documents.
