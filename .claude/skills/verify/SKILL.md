---
name: verify-dashboard
description: Launch and verify the local Codex/Claude usage dashboard through its browser and API surfaces.
---

1. Install dependencies with `npm ci` when `node_modules` is absent.
2. Launch with `npm start`; wait for Vite on `127.0.0.1:8765` and the Python API on `127.0.0.1:8766`.
3. Verify `/data.json?provider=codex` and `/data.json?provider=claude`; confirm Claude responses include `indexing` and do not expose transcript paths or message content.
4. Drive the browser with Python Playwright. A cached Chromium is commonly available at `~/.cache/ms-playwright/*/chrome-linux64/chrome`; pass it as `executable_path`.
5. Click both `button[data-provider]` controls, confirm the URL, title, heading, active button, data-source card, and provider-specific Diagnostics behavior.
6. Repeat two Claude API requests without changing logs; the second should report `scanned_files: 0` and `new_events: 0`.
7. Check a 390px viewport for horizontal page overflow and capture the provider control or a redacted/synthetic screenshot when real aggregate usage is sensitive.
