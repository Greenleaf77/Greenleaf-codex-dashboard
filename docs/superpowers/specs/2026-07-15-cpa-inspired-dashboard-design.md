# CPA-Inspired Dashboard Visual Redesign

## Context

Codex Usage Dashboard already provides the required local usage, cost, chart,
table, and telemetry-diagnostics behavior. This change adapts the visual
language of the supplied reference dashboard without importing its
architecture or changing this project's data model.

The reference is used for visual direction: warm graphite surfaces, large
rounded panels, pill controls, softly colored metric cards, and embedded
trend lines. The implementation remains native HTML, CSS, and vanilla
JavaScript in the existing Vite frontend.

## Goals

- Preserve all current Usage and Diagnostics functionality.
- Make the dashboard feel like a focused local telemetry console rather than
  a generic card grid.
- Adapt the reference project's dark palette, surface hierarchy, controls,
  metric-card composition, and table treatment.
- Keep dense usage data readable at desktop and mobile widths.
- Display compact token values at or above one billion with a `B` suffix.
- Replace the README screenshot with the main Usage view, including the
  complete top metric area.

## Non-goals

- Add a light theme or a theme switcher.
- Add navigation destinations, authentication, request-health metrics, or
  other features from the reference project.
- Change API payloads, token accounting, pricing, filters, chart ranges,
  Diagnostics behavior, or persisted state.
- Add React, chart libraries, icon packages, fonts, or other dependencies.
- Copy the reference project's component code.

## Product Intent

The primary user is a developer opening a local dashboard to understand
where Codex tokens and estimated cost came from. They need to identify scale,
model concentration, cache volume, and suspicious telemetry quickly. The
interface should feel dense, controlled, and instrument-like, while the warm
graphite palette prevents it from feeling like a cold operations terminal.

Domain concepts:

- token flow;
- cache volume;
- model mix;
- local sessions;
- cost estimation;
- time-series activity;
- telemetry replay analysis.

## Visual System

### Color World

The palette is derived from soot, dark metal, warm monitor glass, chalk
labels, and instrument lights:

- canvas: `#151412`;
- primary panel: `#1d1b18`;
- raised or active surface: `#262320`;
- inset surface: `#11100e`;
- soft border: `rgba(201, 195, 187, 0.12)`;
- emphasized border: `rgba(201, 195, 187, 0.2)`;
- primary text: `#f6f4f1`;
- secondary text: `#c9c3bb`;
- tertiary text: `#9c958d`;
- blue, violet, green, cyan, amber, and coral remain semantic metric and
  chart accents.

All colors must be represented by CSS custom properties. Accents communicate
metric identity or state; they are not decorative background noise.

### Depth and Shape

Use subtle surface-color shifts plus quiet borders as the primary depth
strategy. Shadows are reserved for the framed header, active controls, and
metric cards. Panels use approximately 18-24px radii; controls use pill or
10-14px radii according to size. Inputs remain slightly darker than their
parent surfaces.

### Typography

Use the existing system font stack, led by SF Pro on macOS and Segoe UI on
Windows. Metric values use tabular numerals. Headings are bold with slightly
tight tracking; labels use smaller, muted, semibold text. Full table values
remain unsimplified and aligned for comparison.

### Signature

The signature component is an instrument metric card:

- a thin semantic accent line along the top edge;
- a very soft accent wash inside the surface;
- a squared accent icon at the upper right;
- a large tabular value;
- supporting detail below the value;
- a compact sparkline when a meaningful daily numeric series already exists.

The signature appears in the hero metrics and reusable secondary metric
cards. String or date metrics that do not have a meaningful numeric series
keep the same card shell without a fabricated sparkline.

## Layout

### Framed Header

Replace the loose header with one large rounded frame. It contains:

- the Codex Usage brand pill and generated/local-log metadata;
- the ignore-auto-review toggle;
- the main date-range pill group;
- the custom range controls when active.

On narrow widths, controls wrap below the brand without horizontal overflow.
No fake navigation or theme control is introduced.

### Metric Hierarchy

The top metric area is reorganized without removing data:

1. `Total tokens` and `API estimate` become two wide hero cards.
2. Sessions, input, output, total without cache, cached input, active days,
   favorite model, streaks, peak day, and data source remain in an adaptive
   secondary grid.
3. Numeric metrics receive sparklines only when they can be derived from the
   existing `daily` payload. No new API fields are required.

Hero cards must stay visible in the final README screenshot.

### Visualizations

Heatmap and Tokens over time remain mutually exclusive views with their
existing filters and behavior. They move into a larger rounded panel with:

- title and explanatory copy on the left;
- pill view/range controls on the right;
- an inset chart frame;
- chart colors retuned to the warm graphite system while preserving model
  differentiation.

### Usage and Diagnostics

The Usage/Diagnostics switch remains above one shared workspace.

- Usage keeps the Daily Usage and Models tables and all existing expandable
  rows.
- Diagnostics keeps its lazy request, cache, error, loading, and replay
  analysis behavior.
- Both modes use the same panel, pill, border, and table system.

Tables use muted headers, quiet row separators, a restrained hover state,
tabular numeric columns, and the existing horizontal scrolling behavior.

## Number Formatting

Compact metric values use these thresholds:

- below `1,000`: full localized number;
- from `1,000` through values below one million: `k`;
- from one million through values below one billion: `M`;
- at or above `1,000,000,000`: one decimal `B`, for example `1.0B` or
  `4.6B`.

This applies to compact values in metric cards, chart annotations, and
Diagnostics summaries where the existing `compact()` helper is used.
Daily Usage, Models, and Diagnostics table cells continue to use full
localized values.

## Accessibility and Responsive Behavior

- Preserve visible keyboard focus on every control.
- Maintain sufficient text and control contrast against warm dark surfaces.
- Preserve reduced-motion handling for loading indicators.
- Controls and cards wrap cleanly at tablet widths.
- Hero cards stack into one column on mobile.
- Secondary metrics use two columns where possible and one column on narrow
  phones.
- Tables keep horizontal scrolling rather than collapsing or hiding columns.

## Files and Boundaries

Expected implementation scope:

- `src/styles.css`: replace and extend the visual token and component system;
- `src/main.js`: adjust presentation markup, compact formatting, and
  sparkline rendering without changing data fetching or accounting;
- `README.md`: retain the existing usage documentation and add Feature
  bullets for the warm graphite interface, responsive metric hierarchy,
  sparklines, and billion-scale compact formatting;
- `docs/screenshot.png`: replace with the verified main Usage view;
- `CHANGELOG.md`: describe the visual redesign when preparing the next
  release.

Backend files and telemetry tests are not expected to change.

## Basic Validation

- Run the Vite production build.
- Run the existing Python smoke check to ensure the unchanged data path still
  loads.
- Run the focused telemetry unit tests because the redesigned UI consumes the
  same payload.
- Browser-smoke the default Usage view, both visualization modes, main range
  filters, custom dates, model expansion, lazy Diagnostics loading, and the
  return from Diagnostics to Usage.
- Inspect desktop and mobile screenshots for overflow, clipped controls,
  illegible charts, and missing focus states.
- Confirm values at and above one billion render with `B` in compact metric
  contexts while table cells remain full precision.

## Acceptance Criteria

- The dashboard clearly reflects the reference's warm graphite, pill-control,
  rounded-panel, and instrument-card visual language.
- All pre-redesign data, filter, chart, table, model-expansion, and
  Diagnostics behavior remains available.
- No light theme, fake navigation, new dependency, or backend contract is
  added.
- Compact token values at or above one billion use a one-decimal `B`
  representation.
- The final README screenshot shows the main Usage view, the complete top
  metric area, and enough of the visualization/table area to establish the
  new design; it does not show Diagnostics as the active workspace.
