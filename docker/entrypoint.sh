#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$(dirname "${METERMESH_UNIBASE_DB}")"

# Single-process runtime: the Python subclass serves the built SPA from ./dist
# and forwards /api/* and /data.json to the upstream handlers.
exec python3 /app/docker/server.py \
  --host 0.0.0.0 \
  --port 8765 \
  --unibase-db      "${METERMESH_UNIBASE_DB}" \
  --db              "${CODEX_USAGE_DB}" \
  --claude-projects "${CLAUDE_PROJECTS_DIR}" \
  --opencode-db    "${OPENCODE_USAGE_DB}"