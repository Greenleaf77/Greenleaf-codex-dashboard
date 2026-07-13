# Codex Usage Dashboard — visual redesign

Date: 2026-07-12

## Objective

Bring the dashboard visually close to the supplied reference: a compact graphite interface with quiet surface layering, restrained borders, clear numeric hierarchy, and distinctive multicolor icons for every summary metric.

## Scope

This is a presentation-only change. Preserve all existing data, copy, metric order, calculations, API requests, URL state, cookies, filters, chart behavior, heatmap behavior, tables, tooltips, and responsive functionality.

No production dependency will be added. Icons will use inline SVG markup and existing frontend code.

## Visual direction

The interface is for a developer checking Codex activity, token volume, models, and estimated cost at a glance. It should feel like a focused observability console: dense, calm, technical, and legible rather than decorative.

### Domain vocabulary

- Tokens and context
- Sessions and activity
- Model routing
- Cost and cache efficiency
- Streaks and historical usage
- Local Codex logs

### Color world

- Near-black console canvas
- Graphite panels
- Steel-blue chart bars
- Cyan and violet model signals
- Lime activity and cost signals
- Amber achievement signals
- Coral streak signals

Color communicates metric identity and state; it does not tint whole surfaces.

### Signature

Each summary metric receives a specific thin-line icon with a softly tinted circular backing. The icon color matches the metric category and reappears only in closely related chart or status accents.

### Defaults to avoid

- Generic monochrome cards: replaced with category-specific icons and controlled accents.
- Heavy solid borders: replaced with low-opacity separators and subtle surface elevation.
- Monospace everywhere: replaced with a neutral system sans-serif UI while retaining tabular clarity for numbers.

## Layout and components

- Keep the existing page regions and content order.
- Add a compact branded title mark beside the heading.
- Reduce card height and padding to match the reference density.
- Place the icon to the left of each card label and value without changing the metric content.
- Give visualization and table sections the same graphite surface, radius, and border system as cards.
- Restyle segmented controls as quiet inset controls with a clearly raised active state.
- Preserve horizontal overflow for charts and tables on narrow screens.
- On smaller viewports, collapse the metric grid without changing semantic order.

## Design system

- Spacing base: 4px, using consistent multiples.
- Depth: surface color shifts plus restrained borders; shadows only for floating elements such as tooltips.
- Text hierarchy: primary values, secondary labels/headings, tertiary metadata, muted supporting text.
- Controls: inset backgrounds, subtle borders, visible keyboard focus.
- Icons: inline SVG, consistent stroke width, round line caps, decorative icons hidden from assistive technology.

## Implementation boundary

Permitted changes:

- CSS tokens and component styles
- Presentational HTML wrappers and class names
- Inline SVG icon markup
- Responsive layout rules

Not permitted:

- API or Python changes
- Metric definitions or calculations
- Event-handler behavior
- Filter options or defaults
- Data formatting behavior
- Chart aggregation or rendering logic beyond purely visual attributes
- New runtime dependencies

## Validation

- Run the production frontend build.
- Compare the rendered dashboard against the reference at a desktop viewport.
- Check desktop and narrow responsive layouts.
- Exercise range controls, visualization tabs, chart filters, custom dates, checkbox, tooltips, and expandable model rows to confirm unchanged behavior.
- Verify keyboard focus remains visible and the page has no horizontal overflow outside intentional chart/table scrollers.

## Done criteria

- The dashboard closely matches the reference's graphite density and hierarchy.
- Every summary metric has a distinct, polished multicolor icon.
- No data, copy, behavior, or backend code has changed.
- Build and interaction checks pass.
