# Cache-Inclusive Visualizations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan inline, task-by-task. Do not dispatch implementation or review subagents.

**Goal:** Add a shared, URL-persisted `With cache` / `Without cache` control to both visualizations, default to cache-inclusive and auto-review-inclusive data, and prepare version 1.3.0 documentation and screenshot assets.

**Architecture:** Extend the existing chart response with additive cache-inclusive totals while retaining `total_tokens`. Put pure metric and preference resolution in a small frontend module so the new defaults, URL state, and fallback behavior have focused Node tests; keep DOM rendering and event wiring in `src/main.js`.

**Tech Stack:** Python 3.10+, `unittest`, vanilla JavaScript ES modules, Node test runner, Vite, HTML/CSS.

## Global Constraints

- `With cache` is the default visualization accounting mode.
- `Ignore codex-auto-review` is off by default, so auto-review data is included.
- One shared accounting mode governs both Daily heatmap and Tokens over time.
- Switching accounting mode must not refetch usage data.
- Existing tables, metric cards, Diagnostics, pricing, and cost semantics remain unchanged.
- Preserve `total_tokens`; add `total_with_cached_tokens` without removing or redefining fields.
- Add no production dependency and do not introduce a light theme.
- Work inline without subagents; perform a scoped self-review and basic targeted validation.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Add Dual-Metric Chart Aggregation

**Files:**
- Modify: `dashboard_api.py:581-641`
- Test: `tests/test_token_telemetry.py`

**Interfaces:**
- Consumes: deduplicated event dictionaries containing `model`, `day`, `total_tokens`, and `total_with_cached_tokens`.
- Produces: `chart_days_from_events(...)["days"|"models"]` entries containing both `total_tokens: int` and `total_with_cached_tokens: int`.

- [ ] **Step 1: Write the failing backend aggregation test**

Add a focused test that passes two models in one daily bucket and asserts both totals at bucket, nested-model, and chart-model-summary levels:

```python
def test_chart_aggregates_tokens_with_and_without_cached_input(self):
    filters = dashboard_api.resolve_chart_range("30d", None, None, False)
    filters["start_day"] = "2026-07-15"
    filters["end_day"] = "2026-07-15"
    events = [
        dashboard_api.usage_event("t1", "gpt-a", "2026-07-15T10:00:00Z", usage(100, 80, 10), "exact", "usage_update"),
        dashboard_api.usage_event("t2", "gpt-b", "2026-07-15T11:00:00Z", usage(50, 20, 5), "exact", "usage_update"),
    ]

    chart = dashboard_api.chart_days_from_events(events, filters)

    self.assertEqual(chart["days"][0]["total_tokens"], 65)
    self.assertEqual(chart["days"][0]["total_with_cached_tokens"], 165)
    self.assertEqual(
        {row["model"]: row["total_with_cached_tokens"] for row in chart["days"][0]["models"]},
        {"gpt-a": 110, "gpt-b": 55},
    )
    self.assertEqual(
        {row["model"]: row["total_with_cached_tokens"] for row in chart["models"]},
        {"gpt-a": 110, "gpt-b": 55},
    )
```

- [ ] **Step 2: Run the focused test and confirm the red state**

Run: `python3 -m unittest tests.test_token_telemetry.TokenTelemetryTests.test_chart_aggregates_tokens_with_and_without_cached_input`

Expected: FAIL because chart rows do not yet contain `total_with_cached_tokens`.

- [ ] **Step 3: Aggregate both metrics in one pass**

Replace integer-only bucket/model maps with rows that accumulate both keys:

```python
metric_keys = ("total_tokens", "total_with_cached_tokens")
bucket_model_map: dict[str, dict[str, dict[str, int]]] = {}
model_totals: dict[str, dict[str, int]] = {}

for event in events:
    # keep existing bucket resolution
    bucket_totals = bucket_model_map.setdefault(bucket_key, {}).setdefault(
        model, {key: 0 for key in metric_keys}
    )
    overall_totals = model_totals.setdefault(model, {key: 0 for key in metric_keys})
    for key in metric_keys:
        value = int(event[key])
        bucket_totals[key] += value
        overall_totals[key] += value
```

Build nested model rows and summary rows with both totals, and set each bucket's two totals by summing the corresponding nested values. Keep ordering based on `total_tokens` for stable existing model colors.

- [ ] **Step 4: Run the focused backend test**

Run: `python3 -m unittest tests.test_token_telemetry.TokenTelemetryTests.test_chart_aggregates_tokens_with_and_without_cached_input`

Expected: PASS.

---

### Task 2: Add Tested Accounting and Preference Resolution

**Files:**
- Create: `src/visualization-accounting.js`
- Create: `tests/visualization-accounting.test.mjs`
- Modify: `src/main.js:1-175`

**Interfaces:**
- Produces: `WITH_CACHE = "with"`, `WITHOUT_CACHE = "without"`.
- Produces: `resolveCacheMode(value: string | null): "with" | "without"`.
- Produces: `metricValue(row: object, mode: string): number` with cache-inclusive fallback to `total_tokens`.
- Produces: `resolveIgnoreAutoReview(urlValue: string | null, cookieValue: string | null): boolean` using URL, then the new cookie, then `false`.

- [ ] **Step 1: Write failing pure-function tests**

Create `tests/visualization-accounting.test.mjs`:

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import {
  WITH_CACHE,
  WITHOUT_CACHE,
  metricValue,
  resolveCacheMode,
  resolveIgnoreAutoReview
} from "../src/visualization-accounting.js";

test("cache accounting defaults to with cache and accepts explicit modes", () => {
  assert.equal(resolveCacheMode(null), WITH_CACHE);
  assert.equal(resolveCacheMode("invalid"), WITH_CACHE);
  assert.equal(resolveCacheMode(WITHOUT_CACHE), WITHOUT_CACHE);
});

test("metricValue selects the accounting total and safely falls back", () => {
  const row = { total_tokens: 30, total_with_cached_tokens: 100 };
  assert.equal(metricValue(row, WITH_CACHE), 100);
  assert.equal(metricValue(row, WITHOUT_CACHE), 30);
  assert.equal(metricValue({ total_tokens: 30 }, WITH_CACHE), 30);
});

test("auto-review preference uses URL, then the new cookie, then false", () => {
  assert.equal(resolveIgnoreAutoReview("1", "0"), true);
  assert.equal(resolveIgnoreAutoReview("0", "1"), false);
  assert.equal(resolveIgnoreAutoReview(null, "1"), true);
  assert.equal(resolveIgnoreAutoReview(null, null), false);
});
```

- [ ] **Step 2: Run the Node test and confirm the red state**

Run: `node --test tests/visualization-accounting.test.mjs`

Expected: FAIL with module-not-found for `src/visualization-accounting.js`.

- [ ] **Step 3: Implement the pure accounting helpers**

Create `src/visualization-accounting.js`:

```javascript
export const WITH_CACHE = "with";
export const WITHOUT_CACHE = "without";

export function resolveCacheMode(value) {
  return value === WITHOUT_CACHE ? WITHOUT_CACHE : WITH_CACHE;
}

export function metricValue(row, mode) {
  const fallback = Number(row?.total_tokens || 0);
  if (mode !== WITH_CACHE) return fallback;
  const rawInclusive = row?.total_with_cached_tokens;
  const inclusive = rawInclusive === null || rawInclusive === undefined ? Number.NaN : Number(rawInclusive);
  return Number.isFinite(inclusive) ? inclusive : fallback;
}

export function resolveIgnoreAutoReview(urlValue, cookieValue) {
  if (urlValue === "1" || urlValue === "0") return urlValue === "1";
  if (cookieValue === "1" || cookieValue === "0") return cookieValue === "1";
  return false;
}
```

- [ ] **Step 4: Run the focused Node test**

Run: `node --test tests/visualization-accounting.test.mjs`

Expected: 3 tests PASS.

- [ ] **Step 5: Integrate URL and new-cookie state into `src/main.js`**

Import the helpers, change the cookie name to `ignore_codex_auto_review_v2`, parse `cache` and `ignore_auto_review` in `readUrlState()`, and initialize:

```javascript
let cacheMode = initialState.cacheMode;
let ignoreAutoReview = resolveIgnoreAutoReview(
  initialState.ignoreAutoReview,
  readCookie(ignoreAutoReviewCookie)
);
```

Add `cache=${cacheMode}` to `buildQuery()`. Continue writing the new cookie when the ignore control changes; do not read or migrate the legacy cookie.

- [ ] **Step 6: Re-run the focused Node test**

Run: `node --test tests/visualization-accounting.test.mjs`

Expected: 3 tests PASS.

---

### Task 3: Apply the Shared Mode to Both Visualizations

**Files:**
- Modify: `src/main.js:225-390, 690-880`
- Modify: `src/styles.css`
- Test: `tests/visualization-accounting.test.mjs`

**Interfaces:**
- Consumes: `cacheMode`, `WITH_CACHE`, `WITHOUT_CACHE`, and `metricValue(row, cacheMode)` from Task 2.
- Produces: a shared `.accounting-tabs` control with `data-cache-mode="with|without"`.

- [ ] **Step 1: Extend the metric helper test for malformed inclusive values**

Add assertions proving `undefined`, `null`, and non-numeric inclusive values fall back to `total_tokens`; adjust `metricValue` only if the test reveals a mismatch.

- [ ] **Step 2: Make Heatmap consume the selected metric**

Pass `cacheMode` to `heatmapCells()`. Use `metricValue(row, cacheMode)` for the maximum and each cell. Give `renderHeatmap()` a mode label so tooltip and ARIA copy say `tokens with cache` or `tokens without cache`.

- [ ] **Step 3: Make Tokens over time consume the selected metric**

Use `metricValue()` for chart maximums, bucket totals, model segment heights, and tooltip values. Pass `cacheMode` through `renderTokensOverTime()` and `renderChartBar()` so all numeric chart output changes together.

- [ ] **Step 4: Render and wire the shared accounting control**

Insert this group before `.viz-tabs`:

```html
<nav class="segments accounting-tabs" aria-label="Token accounting">
  <button class="seg active" data-cache-mode="with" aria-pressed="true">With cache</button>
  <button class="seg" data-cache-mode="without" aria-pressed="false">Without cache</button>
</nav>
```

Generate active states from `cacheMode`. On click, update `cacheMode`, call `syncUrl()`, and rerender from `currentData` without calling `load()` or `fetch()`.

- [ ] **Step 5: Add responsive control styling**

Reuse existing `.segments` and `.seg` tokens. Add only the minimum layout rules required for `.accounting-tabs` to sit before `.viz-tabs`, remain readable, and wrap within `.viz-controls` at narrow widths.

- [ ] **Step 6: Run frontend checks**

Run: `node --test tests/compact-format.test.mjs tests/visualization-accounting.test.mjs`

Expected: all tests PASS.

Run: `npm run build`

Expected: Vite build exits 0.

---

### Task 4: Prepare Version 1.3.0 Documentation and Screenshot

**Files:**
- Modify: `package.json`
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Rename/replace: `docs/screenshot.png` -> `docs/screenshot-v1.3.0.png`

**Interfaces:**
- Consumes: completed UI from Task 3.
- Produces: versioned release metadata and a cache-busted README asset URL.

- [ ] **Step 1: Update release metadata and documentation**

Set `package.json` version to `1.3.0`. Add a dated `1.3.0` changelog section covering the shared cache accounting selector, cache-inclusive and auto-review-inclusive defaults, additive chart payload, and renamed screenshot. Update the README feature list where appropriate.

- [ ] **Step 2: Update the screenshot reference**

Change the README image target from `docs/screenshot.png?v=1.2.0` to `docs/screenshot-v1.3.0.png`.

- [ ] **Step 3: Run the dashboard and browser-smoke the feature**

Run the existing local launcher on an available dashboard port. Verify:

- first load selects `All`, `With cache`, and unchecked `Ignore codex-auto-review`;
- both accounting modes alter Heatmap intensity/tooltips;
- both accounting modes alter Tokens over time stacks/axis/tooltips;
- switching accounting mode makes no additional `/data.json` request;
- explicit `cache` and `ignore_auto_review` URL values survive reload;
- visualization/range controls still work and the console has no errors.

- [ ] **Step 4: Capture the final README screenshot**

Use the main Usage view with `All time`, `With cache`, and auto-review included. Reduce browser scale until the complete top metric area, heatmap, and at least two Daily Usage rows are visible and readable. Save the new capture as `docs/screenshot-v1.3.0.png`; remove the tracked old screenshot only as part of this rename.

- [ ] **Step 5: Run final targeted validation**

Run:

```bash
python3 -m unittest tests.test_token_telemetry
node --test tests/compact-format.test.mjs tests/visualization-accounting.test.mjs
npm run build
npm run check
```

Expected: all tests pass; Vite build and dashboard smoke check exit 0.

- [ ] **Step 6: Perform inline self-review**

Review `git diff --check`, `git diff --stat`, and the scoped diff. Confirm no unrelated files changed, no old screenshot reference remains, fallback values cannot produce `NaN`, control state is accessible, and the two pre-existing untracked June documents remain untouched.
