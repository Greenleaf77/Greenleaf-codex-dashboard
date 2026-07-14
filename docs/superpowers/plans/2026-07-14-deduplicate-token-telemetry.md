# Deduplicated Codex Token Telemetry Implementation Plan

> **For agentic workers:** Execute inline in this session. Do not use subagents, SDD, or commits unless the user explicitly requests them. Track steps with checkbox (`- [ ]`) syntax.

**Goal:** Replace raw `token_count` summation with deduplicated telemetry accounting and add a lazy, separate Diagnostics view.

**Architecture:** Read each relevant rollout once, classify its entire chronological telemetry stream, and derive Usage, chart, and optional diagnostics aggregates from the shared result. The frontend keeps the existing Usage presentation and lazily fetches diagnostics into a dedicated table workspace.

**Tech Stack:** Python 3.10 standard library, SQLite, JSONL, vanilla JavaScript, CSS, Vite.

## Global Constraints

- Preserve existing Usage table columns and visual hierarchy.
- Do not claim local events are server-accepted or billed.
- Do not add production dependencies, persistent indexes, background jobs, or streaming progress.
- Run only focused backend tests, the existing smoke check, and the frontend build.
- Preserve unrelated untracked documentation files.

---

### Task 1: Classify rollout telemetry once

**Files:**
- Modify: `dashboard_api.py`
- Create: `tests/test_token_telemetry.py`

**Interfaces:**
- Produce `scan_token_telemetry(db_path, start_ts, ignore_auto_review) -> dict` with classified `usage_events` and `token_events` records.
- Produce usage event dictionaries compatible with `token_cost_usd()` and `chart_days_from_events()`.

- [x] Add focused temporary-rollout tests for cumulative increase, replay, baseline, reset, exact response deduplication, and post-classification range filtering.
- [x] Verify the focused tests fail against the current raw-event implementation.
- [x] Add safe usage-component parsing and model-output activity detection.
- [x] Implement exact-event preference and cumulative fallback classification.
- [x] Select threads once using the earliest Usage/chart boundary and scan each rollout from its beginning.
- [x] Run `python3 -m unittest tests/test_token_telemetry.py -v` and expect all focused tests to pass.

### Task 2: Aggregate Usage and optional Diagnostics

**Files:**
- Modify: `dashboard_api.py`
- Modify: `tests/test_token_telemetry.py`

**Interfaces:**
- Extend `load_usage(..., include_diagnostics: bool = False) -> dict`.
- Add `diagnostics` only when requested, with `summary` and `rows` grouped by local hour/model.
- Parse `include_diagnostics` in `DashboardHandler.filters_from_query()` and pass it through both JSON and HTML call paths.

- [x] Add assertions that default payloads omit diagnostics and requested payloads contain consistent reported, deduplicated, and overcount totals.
- [x] Replace both `token_events()` calls with one classified scan and independent in-memory range filters.
- [x] Aggregate diagnostics without changing existing Usage response fields.
- [x] Run the focused unittest and verify aggregate invariants.

### Task 3: Add the separate Diagnostics workspace

**Files:**
- Modify: `src/main.js`
- Modify: `src/styles.css`

**Interfaces:**
- Add a `Usage / Diagnostics` table-view control.
- Add lazy `include_diagnostics=1` loading, filter-keyed memory caching, stale-request cancellation, elapsed loading status, retry, and reduced-motion behavior.

- [x] Extract the current tables into a Usage workspace renderer without changing their markup or columns.
- [x] Render diagnostics summary metrics and the hourly/model audit table only in Diagnostics mode.
- [x] Keep header/cards/chart visible while the diagnostics workspace loads.
- [x] Bind retry and mode controls and prevent aborted responses from replacing current data.
- [x] Run `npm run build` and expect Vite to complete without errors.

### Task 4: Self-review and basic validation

**Files:**
- Review only the files listed above and the two new documents.

- [x] Review the diff for unrelated changes, naming that overclaims server behavior, and consistency with existing patterns.
- [x] Run `python3 -m unittest tests/test_token_telemetry.py -v`.
- [x] Run `npm run check` against the configured local database.
- [x] Run `npm run build`.
- [x] Smoke the API with and without `include_diagnostics=1`; confirm the default omits diagnostics and the optional response is internally consistent.
