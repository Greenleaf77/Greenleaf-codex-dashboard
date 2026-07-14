# Deduplicated Codex Token Telemetry Design

## Problem

The dashboard currently treats every persisted `token_count.last_token_usage` value as a new model completion. Codex can emit `token_count` again when only rate limits or compaction state changes, while `total_token_usage` remains unchanged. Summing those replayed snapshots inflates token totals, apparent calls, and estimated cost.

The local rollout history is telemetry, not a server billing ledger. The dashboard must make that distinction explicit and must not claim that a locally observed event was accepted or billed by OpenAI.

## Goals

- Base Usage totals and cost on deduplicated local telemetry.
- Prefer exact, non-replayed upstream completion usage when future rollouts persist `raw_response_completed`.
- Correctly classify cumulative `token_count` snapshots from the beginning of a rollout even when the selected date range starts later.
- Expose replay and overcount evidence only in an optional Diagnostics view.
- Keep the existing Usage tables visually unchanged.
- Avoid multiplying rollout scans when the main and chart ranges differ.

## Non-goals

- Reconstruct HTTP request counts or rejected requests.
- Guarantee equality with OpenAI server-side usage statistics.
- Change pricing sources or cache-write accounting.
- Add persistent indexes, background jobs, streaming progress, or new dependencies.

## Telemetry Sources and Classification

Each selected rollout is read chronologically from its beginning. Date filters are applied only after events are classified, so the first event inside a selected range receives the correct cumulative baseline.

Usage source priority is:

1. `raw_response_completed.token_usage`, deduplicated by `response_id`, when present. It represents exact usage for one upstream Responses API completion.
2. `token_count.info.total_token_usage` cumulative component deltas as a fallback.

Each valid exact event suppresses only its following cumulative snapshot. Cumulative fallback remains available before exact telemetry is introduced and whenever an exact completion has no token usage.

The fallback compares cumulative components (`input_tokens`, `cached_input_tokens`, `output_tokens`, and `reasoning_output_tokens`); derived `total_tokens` is not used for equality or reset detection.

- `usage_update`: one or more cumulative components increased; contribute the positive component deltas.
- `replayed_event`: all cumulative components are unchanged; contribute zero.
- `baseline_event`: the first cumulative snapshot has no preceding model-output activity; contribute zero.
- `counter_reset`: any cumulative component decreased. Start a new epoch and contribute `last_token_usage` only when model-output activity preceded the snapshot.
- `unverifiable_event`: cumulative data is missing or malformed. Contribute valid `last_token_usage` only when model-output activity preceded the snapshot.

Model-output activity means a persisted assistant message, reasoning item, or model-issued tool call since the preceding token snapshot. User/developer messages, compaction records, tool outputs, and rate-limit-only updates do not qualify.

Billable non-cached input remains `max(input_tokens - cached_input_tokens, 0)`. Cost is recomputed from the deduplicated components using the existing pricing logic.

## Data Flow and Performance

One scanner selects relevant threads using the earliest boundary required by the Usage and chart filters, then reads each selected rollout once. It produces one classified event stream. Usage, chart, and optional Diagnostics aggregations filter that shared stream independently.

The scanner always performs the classification needed for correct Usage totals. Detailed diagnostics rows are aggregated and returned only when `include_diagnostics=1`. No persistent cache is required: cumulative state is reconstructed from the rollout on every dashboard/API load, including the first load.

## Diagnostics API

`/data.json` and `/api/usage` accept `include_diagnostics=1`. The default response omits the `diagnostics` field.

The diagnostics payload contains:

- summary counts: raw token events, deduplicated usage updates, replayed events, baseline events, counter resets, unverifiable events, exact usage events, and fallback usage events;
- reported token volume from raw `last_token_usage` snapshots;
- deduplicated token volume from classified local usage updates;
- estimated local overcount (`max(reported - deduplicated, 0)`);
- rows grouped by local hour and model with the same core event and token-volume measures.

Labels use “Deduplicated usage updates” rather than “accepted calls.” Explanatory copy states that results are local replay analysis and may be closer to upstream usage, but are not server billing data.

## Interface

A compact segmented control above the table area switches between `Usage` and `Diagnostics`.

- `Usage` is the default and renders the existing Daily Usage and Models tables without added diagnostic columns.
- `Diagnostics` is a separate audit workspace with four concise summary metrics and one hourly/model table: Hour, Model, Raw events, Updates, Replayed, Replay rate, Reported total, Deduplicated total, and Estimated overcount.
- The existing header, aggregate cards, and visualization remain visible in both modes.

Diagnostics are fetched lazily on first activation and cached in memory by active usage range and auto-review filter. Changing those filters aborts stale work and invalidates the relevant view. Switching back to an already loaded diagnostics key is immediate.

While loading, only the table workspace shows a spinner and `Analyzing rollout telemetry…`; after two seconds it also shows elapsed time. The UI does not show fake percentage progress. Failures show a compact retry action. Spinner motion is disabled when `prefers-reduced-motion: reduce` is active.

Initial and filter-driven Usage loads use the same honest spinner and elapsed-time treatment because a full chronological scan can take several seconds.

## Error Handling

- Missing rollout files and malformed JSON lines continue to be skipped without exposing local content.
- Malformed cumulative usage is classified as unverifiable rather than silently treated as confirmed usage.
- A failed lazy Diagnostics request does not remove already rendered Usage data.
- An aborted stale request does not replace a newer result or display an error.

## Basic Validation

- A focused backend test covers monotonic cumulative deltas, unchanged replay, a first baseline, a counter reset, exact response ID deduplication, and filtering after classification.
- The existing Python smoke check verifies aggregate invariants on the real configured database.
- The Vite production build verifies the frontend module and CSS.
- A manual browser smoke checks the mode switch, lazy loading, cache reuse, retry state, and unchanged Usage tables.

## Acceptance Criteria

- Unchanged cumulative snapshots never increase Usage tokens or cost.
- A cumulative increase contributes only its component deltas.
- The first replayed snapshot after resume/compaction is a zero-usage baseline, while a first snapshot preceded by model output can contribute valid `last_token_usage`.
- A date-limited request classifies against earlier rollout history before filtering.
- A rollout is not reread separately for Usage, chart, and Diagnostics in one API request.
- Default API responses contain no diagnostics payload.
- Diagnostics remain outside the existing Usage tables and include accessible loading, error, and reduced-motion states.
