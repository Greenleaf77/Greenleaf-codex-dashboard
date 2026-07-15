# Cache-Inclusive Visualizations Design

## Context

The dashboard's Daily heatmap and Tokens over time views currently visualize
`total_tokens`, which excludes cached input. The Daily Usage payload already
contains both the cache-exclusive total and `total_with_cached_tokens`, but the
chart payload exposes only the cache-exclusive metric. Users need to compare
working-context volume with and without cached input without changing the
meaning of tables, metric cards, or cost estimates.

This change is planned for version 1.3.0. It also establishes cache-inclusive
visualization and inclusion of `codex-auto-review` as the default dashboard
state.

## Goals

- Add one shared `With cache` / `Without cache` accounting control to the
  visualization panel.
- Apply the selected accounting mode consistently to Daily heatmap and Tokens
  over time.
- Make `With cache` the default when no explicit URL state is present.
- Make `Ignore codex-auto-review` disabled by default, so auto-review usage is
  included when no explicit URL state is present.
- Preserve explicit URL state for reproducible dashboard views.
- Keep mode changes immediate, without refetching usage data.
- Rename the README screenshot asset for reliable cache invalidation.

## Non-goals

- Change the accounting shown in top metric cards, Daily Usage, Models, or
  Diagnostics.
- Change pricing or cost calculations.
- Claim that either visualization metric equals server-side billing data.
- Add a new chart library, framework, dependency, or backend endpoint.
- Add separate cache controls for each visualization.

## Product Intent

The primary user is a developer reconciling local Codex telemetry. They need
to distinguish two useful views of the same activity:

- `With cache`: total model context volume, including cached input;
- `Without cache`: non-cached input plus output, matching the dashboard's
  existing cache-exclusive visualization behavior.

The interface should remain dense, instrument-like, and trustworthy. The
accounting choice must be explicit and must affect the complete visualization,
not merely its labels.

## Chosen Data Design

The API returns both accounting metrics in one response. This is preferred to
refetching on every toggle because it keeps the control immediate and avoids a
second loading state. It is also preferred to reconstructing chart data in the
browser because chart buckets and per-model stacks are produced by the backend.

Existing fields remain backward compatible:

- `total_tokens`: cache-exclusive tokens;
- `total_with_cached_tokens`: tokens including cached input.

Daily Usage rows already contain both fields and require no contract change.
The chart payload gains `total_with_cached_tokens` alongside `total_tokens` at
both aggregation levels:

- each chart bucket/day;
- each model entry inside a chart bucket/day;
- each model summary entry used by the chart legend and model ordering.

The backend calculates both values from the same deduplicated event stream and
the same bucket boundaries. It does not rescan rollouts or issue another API
request when the user changes the display mode.

## Interface and Interaction

### Accounting Control

A compact two-option segmented control appears in the visualization header,
immediately before the existing `Daily heatmap` / `Tokens over time` control:

- `With cache`;
- `Without cache`.

It reuses the current graphite pill-control system rather than introducing a
generic on/off switch or a new accent color. The selected option uses the same
active-surface treatment as the existing visualization controls.

The control is shared across both visualization views. Switching between
Daily heatmap and Tokens over time preserves the selected accounting mode.
The control wraps with the existing header controls at narrow widths without
causing horizontal overflow.

The segmented group has an accessible name such as `Token accounting`.
Buttons expose their selected state through the existing tab semantics or
`aria-pressed`, consistently with nearby controls. Keyboard focus remains
visible.

### Default and URL State

When the URL contains no accounting preference, `With cache` is active. The
chosen accounting mode is written as `cache=with|without` and restored on
reload or link sharing. An explicit valid URL value overrides the default; an
absent or invalid value falls back to `With cache`.

When the URL contains no auto-review preference, `Ignore codex-auto-review`
is off and auto-review usage is included. The existing
`ignore_auto_review=0|1` URL value is authoritative when present. Otherwise a
new versioned preference cookie is used, falling back to `false`. The legacy
cookie is not migrated because its `true` value was previously created as an
automatic default and cannot be distinguished from an intentional choice.
After the user changes the control, the new cookie preserves that choice.
This changes only default-state resolution, not the meaning of the control.

### Daily Heatmap

In `With cache` mode, each cell, the heat-scale maximum, intensity levels,
tooltip, and accessible label use `total_with_cached_tokens`. In `Without
cache` mode, they use `total_tokens`.

Changing the mode rerenders the heatmap immediately from the already loaded
Daily Usage payload. Dates, range selection, and activity-day layout remain
unchanged.

### Tokens Over Time

The selected metric controls every numeric part of the chart:

- bucket totals;
- per-model stacked segments;
- vertical scale and tick labels;
- hover/tooltip values;
- any total annotation derived from chart values.

The date range, bucket granularity, model colors, model ordering, and legend
remain unchanged. Switching accounting mode does not alter the selected chart
range or trigger a network request.

## Visual Direction

The feature extends the version 1.2 warm graphite system:

- canvas and panels remain soot/graphite surfaces;
- active controls remain raised graphite pills;
- chart model colors keep their semantic identity;
- no additional decorative color is introduced.

The signature interaction is an explicit accounting selector integrated into
the instrument header. It makes the same cached-input choice visibly govern
both heat intensity and stacked token volume.

Rejected interface patterns:

- a generic switch, because the two accounting modes should be named;
- separate controls inside each chart, because their state could diverge;
- fetching a second dataset after each click, because the interaction should
  be immediate and deterministic.

## Documentation and Release Assets

- Prepare the changelog entry for version 1.3.0 describing the shared cache
  accounting control and the new defaults.
- Rename `docs/screenshot.png` to `docs/screenshot-v1.3.0.png` and update the
  README reference so GitHub/CDN caches receive a new asset URL.
- Capture the main Usage view using `All time`, `With cache`, and included
  `codex-auto-review` data. The image must include the top metric cards, the
  heatmap, and at least two Daily Usage rows at a reduced browser scale.
- Do not use Diagnostics as the active view in the README screenshot.

## Compatibility and Error Handling

- Existing API consumers can continue using `total_tokens`; no field is
  removed or redefined.
- If an older or malformed payload lacks a cache-inclusive chart value, the
  frontend falls back safely to the cache-exclusive value rather than
  rendering `NaN` or an empty chart.
- Empty ranges render the existing empty visualization state in either mode.
- Invalid accounting URL values are normalized to the default `With cache`
  mode.

## Basic Validation

- Add a focused backend test proving that chart buckets and per-model entries
  contain correct cache-exclusive and cache-inclusive totals.
- Add focused frontend coverage for accounting-mode selection, default URL
  state, and fallback behavior where practical within the existing test
  structure.
- Run the Vite production build.
- Browser-smoke both accounting modes in Daily heatmap and Tokens over time,
  confirm that axes/intensity/tooltips change consistently, and confirm no
  additional data request is made by the toggle.
- Verify that explicit accounting and auto-review URL values survive reload,
  while missing values use the new defaults.
- Inspect the reduced-scale README screenshot for readable controls, visible
  top cards, heatmap, and at least two table rows.

## Acceptance Criteria

- `With cache` is the default visualization accounting mode when no explicit
  URL state is present.
- `Ignore codex-auto-review` is off by default when no explicit URL state is
  present.
- One shared control switches both visualizations and persists across view
  changes and reloads.
- Heatmap intensity and labels use the selected accounting metric.
- Tokens over time totals, stacks, scale, and labels use the selected
  accounting metric.
- Switching modes is immediate and does not refetch data.
- The API exposes both totals additively without changing existing field
  semantics.
- Tables, cards, Diagnostics, pricing, and cost accounting remain unchanged.
- README references `docs/screenshot-v1.3.0.png`, and the screenshot shows the
  agreed main Usage composition.
