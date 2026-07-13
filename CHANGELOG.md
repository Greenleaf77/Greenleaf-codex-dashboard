# Changelog

## 1.0.4 - 2026-07-13

- Redesigned the dashboard with a compact graphite visual system.
- Added distinct multicolor inline SVG icons for every summary metric.
- Improved responsive controls, keyboard focus, and reduced-motion support without changing dashboard behavior.

## 1.0.3 - 2026-06-28

- Added visualization tabs for `Daily heatmap` and `Tokens over time`.
- Added a stacked tokens-over-time bar chart split by model.
- Added independent chart date filters: all time, 1 year, 6 months, 90 days, 30 days, and custom dates.
- Added adaptive chart buckets: daily through 60 days, weekly through 6 months, and monthly for longer ranges.
- Updated the README screenshot for the new chart view.

## 1.0.2 - 2026-06-07

- Added Windows-friendly Python command resolution for the launcher and smoke-check.
- Added cached input token visibility while preserving the original total-without-cached token accounting.
- Added a total-with-cached token metric for daily usage, model breakdowns, and summary cards.
- Added 1-day and custom date range filters.
- Added an option to ignore the `codex-auto-review` model.
- Added expandable daily details for each model.
- Thanks @nisaev for the pull request that contributed the Windows support and cached-token dashboard improvements.

## 1.0.1 - 2026-05-28

- Added API-equivalent USD cost estimates for totals, daily usage, and model breakdowns.
- Fetches current model pricing from LiteLLM at dashboard load time, with bundled fallback prices for known Codex models.
- Documents that historical cost estimates are recalculated with the current price table.

## 1.0.0 - 2026-05-27

- Initial open-source release.
