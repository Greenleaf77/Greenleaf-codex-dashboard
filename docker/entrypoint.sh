#!/usr/bin/env bash
# Single-process MeterMesh runtime.
# The Python subclass serves the built SPA from ./dist for / and /assets/*
# and falls through to the upstream handlers for everything else (including
# /api/* and /data.json).
#
# Compose's `user:` directive pins the running UID/GID, so we don't drop
# privileges here. The container needs to read $HOME-absolute source paths
# (Codex state_5.sqlite stores host-absolute rollout paths), so HOME is set
# in the compose `environment` block to match the host.

set -euo pipefail

exec python3 /app/docker/server.py \
  --host 0.0.0.0 \
  --port 8765 \
  --unibase-db      "${METERMESH_UNIBASE_DB}" \
  --db              "${CODEX_USAGE_DB}" \
  --claude-projects "${CLAUDE_PROJECTS_DIR}" \
  --opencode-db    "${OPENCODE_USAGE_DB}"