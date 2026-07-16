---
name: verify-dashboard
description: Launch and verify MeterMesh through its browser, Unibase, and API surfaces.
---

1. Install dependencies with `npm ci` when `node_modules` is absent.
2. Launch with `npm start`; wait for Vite on `127.0.0.1:8765` and the Python API on `127.0.0.1:8766`.
3. Verify `/api/usage` for `all`, `codex`, `claude`, and `opencode`; confirm All equals the provider scopes and responses expose no paths, prompts, tools, raw IDs, credentials, or account identity.
4. Drive the browser with Python Playwright. A cached Chromium is commonly available at `~/.cache/ms-playwright/*/chrome-linux64/chrome`; pass it as `executable_path`.
5. Confirm the stable MeterMesh heading and neutral mesh mark, then click All, Codex, Claude, and OpenCode in that order. Verify title, URL, active provider, model labels, and Diagnostics.
6. Verify Usage, Diagnostics, and Requests. Exercise every Requests grouping, Previous/Next pagination, and one expanded grouped branch without an additional network request.
7. Open Settings and verify the three backup groups, local draft/Cancel behavior, dirty-state maintenance lockout, revision handling, and safe relative source names.
8. Exercise Reset only with a synthetic Unibase and exact `RESET UNIBASE` confirmation. Verify `reset_empty`, then run Full reindex and poll progress to success.
9. Check keyboard focus, Escape/Cancel dialog behavior, reduced motion, and a 390px viewport with no page overflow.
10. Capture `docs/screenshot-v2.0.0.png` only from synthetic/redacted data when real aggregate usage is sensitive.
