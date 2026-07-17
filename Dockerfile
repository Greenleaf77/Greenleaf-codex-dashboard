# syntax=docker/dockerfile:1.7

# ---- Stage 1: build the Vite frontend ----
FROM node:24-bookworm-slim AS frontend-builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    METERMESH_UNIBASE_DB=/data/unibase/unibase.sqlite3 \
    CODEX_USAGE_DB=/data/sources/codex/state_5.sqlite \
    CLAUDE_PROJECTS_DIR=/data/sources/claude/projects \
    OPENCODE_USAGE_DB=/data/sources/opencode/opencode.db \
    METERMESH_ALLOW_REMOTE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata bash \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 metermesh \
 && useradd  --system --uid 10001 --gid metermesh \
             --home-dir /home/metermesh --shell /usr/sbin/nologin metermesh

WORKDIR /app

COPY --from=frontend-builder /app/dist ./dist
COPY dashboard_api.py unibase.py codex_usage.py claude_usage.py opencode_usage.py ./
COPY docker/ ./docker/

RUN chmod +x docker/entrypoint.sh \
 && mkdir -p /data/unibase /data/sources \
 && chown -R metermesh:metermesh /app /data

USER metermesh

EXPOSE 8765

ENTRYPOINT ["/app/docker/entrypoint.sh"]