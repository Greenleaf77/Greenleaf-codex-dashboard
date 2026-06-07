# Changelog

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
