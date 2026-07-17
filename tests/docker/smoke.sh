#!/usr/bin/env bash
#
# Docker smoke test for the MeterMesh container.
#
# Covers the three scenarios the read-only sandbox design has to survive:
#   1. Source dirs are private (0700) and owned by the invoking user.
#   2. Fresh install: no add_stat/ exists in any source dir before start.
#   3. Codex state_5.sqlite holds host-ABSOLUTE rollout paths that must resolve
#      identically inside the container.
#
# Every assertion below names the mutation it catches. An assertion that cannot
# name one is not worth running.
#
# Usage: tests/docker/smoke.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FIXTURES_HOME="$SCRIPT_DIR/fixtures/home"
COMPOSE_FILE="$REPO_ROOT/docker-compose.yml"
PROJECT="metermesh-smoke"
BASE_URL="http://127.0.0.1:8765"

# docker-compose.yml interpolates ${HOME} to build the same-path mounts, so we
# point HOME at the fixtures tree. Docker's own credential/config lookup also
# keys off HOME, so pin DOCKER_CONFIG to the real one before we clobber it.
export DOCKER_CONFIG="${DOCKER_CONFIG:-$HOME/.docker}"
REAL_HOME="$HOME"
UID_VAL="$(id -u)"
GID_VAL="$(id -g)"

ADD_STAT_DIRS=(
  "$FIXTURES_HOME/.codex/add_stat"
  "$FIXTURES_HOME/.claude/add_stat"
  "$FIXTURES_HOME/.local/share/opencode/add_stat"
)
SOURCE_DIRS=(
  "$FIXTURES_HOME/.codex"
  "$FIXTURES_HOME/.claude"
  "$FIXTURES_HOME/.local/share/opencode"
)
MISSING_SOURCE="$FIXTURES_HOME/.local/share/opencode"
MISSING_SOURCE_BACKUP="$FIXTURES_HOME/.local/share/opencode.smoke-missing"

FAILURES=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
info() { printf '\n== %s\n' "$1"; }

check_eq() { # expected actual label
  if [ "$1" = "$2" ]; then pass "$3 ($2)"; else fail "$3: expected '$1', got '$2'"; fi
}

host_mode() { # path -> octal permission bits of a host file
  # Branch on the OS rather than on exit status: GNU `stat -f` is
  # --file-system, not a format flag, so it prints filesystem stats and fails
  # on the format string as a missing operand -- meaning a
  # `stat -f ... || stat -c ...` chain runs BOTH and concatenates their output.
  if [ "$(uname -s)" = "Darwin" ]; then stat -f '%Lp' "$1"; else stat -c '%a' "$1"; fi
}

compose() { # runs compose with the fixtures HOME + host UID/GID
  HOME="$FIXTURES_HOME" METERMESH_UID="$UID_VAL" METERMESH_GID="$GID_VAL" \
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

teardown() {
  local status=$?
  info "Teardown"
  compose down -v >/dev/null 2>&1 || true
  # Leave the fixtures exactly as committed: no generated dbs, no add_stat.
  rm -rf "${ADD_STAT_DIRS[@]}"
  rm -f "$FIXTURES_HOME/.codex/state_5.sqlite" \
        "$FIXTURES_HOME/.local/share/opencode/opencode.db"
  if [ -d "$MISSING_SOURCE_BACKUP" ] && [ ! -e "$MISSING_SOURCE" ]; then
    mv "$MISSING_SOURCE_BACKUP" "$MISSING_SOURCE"
  fi
  chmod 755 "${SOURCE_DIRS[@]}" 2>/dev/null || true
  echo "  torn down"
  exit "$status"
}
trap teardown EXIT INT TERM

reset_fixtures() {
  rm -rf "${ADD_STAT_DIRS[@]}"
  python3 "$SCRIPT_DIR/make_fixtures.py" "$FIXTURES_HOME" >/dev/null
  # Scenario 1: sources are private to the invoking user.
  chmod 700 "${SOURCE_DIRS[@]}"
}

wait_for_http() { # url timeout_seconds
  local deadline=$((SECONDS + $2))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if [ "$(curl -s -o /dev/null -w '%{http_code}' "$1" || true)" = "200" ]; then return 0; fi
    sleep 1
  done
  return 1
}

# --------------------------------------------------------------------------
info "Preflight"
# docker-compose.yml pins `container_name: metermesh`, so the name is global and
# no two compose projects can hold it at once. Detect a foreign holder up front
# rather than letting `up` die with a raw daemon conflict. We refuse to remove a
# container this test did not create.
OWNER="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' metermesh 2>/dev/null || true)"
if [ -n "$OWNER" ] && [ "$OWNER" != "$PROJECT" ]; then
  echo "  container 'metermesh' is already held by compose project '$OWNER'."
  echo "  docker-compose.yml hardcodes container_name, so this test cannot run alongside it."
  echo "  Stop it first (its index volume is preserved):"
  echo "      docker compose -p $OWNER -f $COMPOSE_FILE down"
  exit 1
fi
echo "  no conflicting 'metermesh' container"

info "Build"
compose build >/dev/null
echo "  built metermesh:local"

# --------------------------------------------------------------------------
# catches: replacing long bind syntax with short syntax, which silently creates
# a missing host source directory as root. The shipped config must fail before
# startup and leave the host path absent.
info "Fail-fast missing source bind"
reset_fixtures
rm -rf "$MISSING_SOURCE_BACKUP"
mv "$MISSING_SOURCE" "$MISSING_SOURCE_BACKUP"
if compose up -d >/tmp/metermesh-smoke-missing-source.log 2>&1; then
  fail "compose started with a missing source directory"
else
  pass "compose rejected a missing source directory"
fi
if [ -e "$MISSING_SOURCE" ]; then
  fail "Docker created the missing source directory on the host"
else
  pass "missing source directory was not created on the host"
fi
compose down -v >/dev/null 2>&1 || true
mv "$MISSING_SOURCE_BACKUP" "$MISSING_SOURCE"

# --------------------------------------------------------------------------
# Scenario 2: fresh install. A never-indexed source has no add_stat/, and the
# read-only bind means one can never be created: mkdir reports EROFS, which
# exist_ok does not absorb. discover_backup_sources() swallows that and reports
# no backups, so the live source still registers and the server still boots.
info "Scenario 2: fresh install with no add_stat/ present"
compose down -v >/dev/null 2>&1 || true
reset_fixtures
for dir in "${ADD_STAT_DIRS[@]}"; do
  if [ -e "$dir" ]; then fail "precondition: $dir exists before start"; fi
done
pass "precondition: no add_stat/ in any fixture source dir"

# catches: restoring the unguarded add_stat.mkdir() in unibase.py -> EROFS kills
# the server at bootstrap. Also catches: reintroducing a `tmpfs:` mount over
# add_stat -> runc cannot create the mountpoint inside the read-only bind and
# the container never starts. Also catches: any Dockerfile/entrypoint change
# that stops the process booting at all.
if compose up -d >/dev/null 2>&1; then
  pass "container started from a fresh (add_stat-free) source tree"
else
  fail "container FAILED to start from a fresh source tree"
  echo "  --- compose error ---"
  compose up -d 2>&1 | sed 's/^/  /' | tail -6 || true
  echo "  ---------------------"
  exit 1
fi

# catches: dropping `:ro` from the source binds -> mkdir(add_stat) succeeds
# against the real host dir and leaks an add_stat/ into the user's ~/.codex.
LEAKED=0
for dir in "${ADD_STAT_DIRS[@]}"; do
  if [ -e "$dir" ]; then
    fail "add_stat/ leaked onto host: $dir"
    LEAKED=1
  fi
done
if [ "$LEAKED" -eq 0 ]; then pass "no add_stat/ leaked onto the host fixture dirs"; fi

# --------------------------------------------------------------------------
info "Readiness and API surface"

# catches: METERMESH_ALLOW_REMOTE removed (server refuses to bind 0.0.0.0 and
# exits), port mapping changed, or docker/server.py failing to import.
if wait_for_http "$BASE_URL/api/unibase/status" 60; then
  pass "GET /api/unibase/status returned 200"
else
  fail "GET /api/unibase/status never returned 200"
  echo "  --- container logs ---"; docker logs metermesh 2>&1 | tail -20 | sed 's/^/  /'
  exit 1
fi

# Pin the single-process static/API split: the container serves the built SPA,
# keeps the compatibility JSON endpoint on the upstream handler, and does not
# turn missing assets into HTML responses.
INDEX_CODE="$(curl -s -o /tmp/metermesh-smoke-index.html -w '%{http_code}' "$BASE_URL/")"
check_eq "200" "$INDEX_CODE" "GET / served the built SPA"
if grep -q '<main id="app"></main>' /tmp/metermesh-smoke-index.html; then
  pass "GET / returned the Vite index"
else
  fail "GET / did not return the Vite index"
fi

DATA_CODE="$(curl -s -o /tmp/metermesh-smoke-data.json -w '%{http_code}' "$BASE_URL/data.json?provider=all")"
check_eq "200" "$DATA_CODE" "GET /data.json reached the API handler"
if python3 -c 'import json; json.load(open("/tmp/metermesh-smoke-data.json"))'; then
  pass "GET /data.json returned JSON"
else
  fail "GET /data.json did not return JSON"
fi

MISSING_ASSET_CODE="$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/assets/missing-smoke-file.js")"
check_eq "404" "$MISSING_ASSET_CODE" "missing static assets return 404"

# POST /api/unibase/resync wants Content-Type: application/json and a literal
# `{}`; read_json_body() rejects a zero-length body with 400.
# catches: the /api/unibase/resync route being renamed or removed (-> 404).
RESYNC_CODE="$(curl -s -X POST -H 'Content-Type: application/json' -d '{}' \
  -o /tmp/metermesh-smoke-resync.json -w '%{http_code}' "$BASE_URL/api/unibase/resync")"
check_eq "202" "$RESYNC_CODE" "POST /api/unibase/resync accepted"

OPERATION_ID="$(python3 -c 'import json;print(json.load(open("/tmp/metermesh-smoke-resync.json"))["operation_id"])')"

# catches: any source raising during import -- resync_worker collects per-source
# errors and fails the whole operation. A missing/unreadable mount lands here.
OP_STATE="none"
DEADLINE=$((SECONDS + 60))
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  curl -s "$BASE_URL/api/unibase/status?operation_id=$OPERATION_ID" -o /tmp/metermesh-smoke-op.json
  OP_STATE="$(python3 -c 'import json;o=json.load(open("/tmp/metermesh-smoke-op.json"))["operation"];print(o["state"] if o else "none")')"
  case "$OP_STATE" in succeeded|failed) break;; esac
  sleep 1
done
check_eq "succeeded" "$OP_STATE" "resync operation completed"
if [ "$OP_STATE" = "failed" ]; then
  python3 -c 'import json;print("  error:",json.load(open("/tmp/metermesh-smoke-op.json"))["operation"]["error"])'
fi

# --------------------------------------------------------------------------
info "Scenario 3: host-absolute Codex rollout paths + indexed data"
curl -s "$BASE_URL/api/usage?provider=all&range=all&timezone=UTC" -o /tmp/metermesh-smoke-usage.json
curl -s "$BASE_URL/api/settings" -o /tmp/metermesh-smoke-settings.json

# Flatten both payloads into shell assignments in one pass. Kept in a real
# file rather than an inline heredoc: bash tracks quotes through $( ... ) even
# for a quoted heredoc, so an apostrophe in a Python comment breaks parsing.
eval "$(python3 "$SCRIPT_DIR/probe.py" /tmp/metermesh-smoke-usage.json /tmp/metermesh-smoke-settings.json)"

# catches: reverting the same-path mount to `${HOME}/.codex:/data/sources/codex`.
# The archive rollout lives outside <home>/.codex/sessions/, so the relative glob
# never sees it; it is indexed only when state_5.sqlite's host-absolute
# rollout_path resolves inside the container. Verified against the mutation: the
# whole 2026-01-02 row disappears.
check_eq "9001" "$ARCHIVE_INPUT" "archive rollout input_tokens (absolute path resolved)"
check_eq "9102" "$ARCHIVE_OUTPUT" "archive rollout output_tokens"
check_eq "9103" "$ARCHIVE_REASONING" "archive rollout reasoning_tokens"

# catches: the same mount revert, independently of the row above.
# import_codex_source() prefers state_5.sqlite's model and falls back to the
# JSONL session_meta model when the absolute path misses. Verified against the
# mutation: model_key flips to codex:smoke-codex-meta-model.
check_eq "1" "$CODEX_STATE_MODEL" "codex model came from state_5.sqlite"
check_eq "0" "$CODEX_META_MODEL" "codex model did NOT fall back to rollout metadata"

# catches: the mount revert leaving only the glob-discovered rollout (files=1).
check_eq "2" "$CODEX_FILES" "codex indexed both rollouts"

# catches: the mount revert -> import_codex_source marks the source
# 'Codex state inventory is incomplete; retained committed data'.
check_eq "ready" "$CODEX_STATUS" "codex source is not in an error state"
check_eq "0" "$CODEX_SOURCE_ERROR" "codex source carries no error"
if [ "$CODEX_SOURCE_ERROR" = "1" ]; then
  docker exec metermesh python3 -c '
import os, sqlite3
from pathlib import Path
db = Path(os.environ["CODEX_USAGE_DB"])
print("  diagnostic: HOME=", os.environ.get("HOME"), " state_db=", db, " exists=", db.exists(), sep="")
if db.exists():
    with sqlite3.connect(db) as conn:
        for (path,) in conn.execute("select rollout_path from threads order by rollout_path"):
            print("  diagnostic: rollout_path=", path, " exists=", Path(path).is_file(), sep="")
' || true
fi

# catches: the ${HOME}/.codex bind being dropped entirely, or CODEX_USAGE_DB
# pointing somewhere the sessions tree isn't. (7001 raw - 1 cached = 7000.)
check_eq "7000" "$SESSIONS_INPUT" "sessions rollout input_tokens"

# catches: dropping the ${HOME}/.claude bind, or CLAUDE_PROJECTS_DIR pointing at
# any path the compose file does not mount -> no claude rows.
check_eq "3001" "$CLAUDE_INPUT" "claude input_tokens"
check_eq "3002" "$CLAUDE_OUTPUT" "claude output_tokens"

# catches: dropping the opencode bind, or OPENCODE_USAGE_DB pointing at any path
# the compose file does not mount -> resync fails.
check_eq "5001" "$OPENCODE_INPUT" "opencode input_tokens"
check_eq "5002" "$OPENCODE_OUTPUT" "opencode output_tokens"

# --------------------------------------------------------------------------
# These are NOT platform-gated. The Unibase index lives on a named volume, and a
# named volume is a Linux filesystem inside the daemon (the Docker Desktop VM on
# darwin), so its seeding semantics are identical on both hosts. Verified on
# darwin: a fresh volume seeds mode/owner from the image's /data/unibase, and a
# container running as a non-10001 UID gets "permission denied" at mode 755.
info "Runtime identity and index writability"

# catches: removing `user:` from docker-compose.yml -> the container runs as the
# baked-in UID 10001 instead of the invoking user.
CONTAINER_UID="$(docker exec metermesh id -u 2>/dev/null || echo '-')"
check_eq "$UID_VAL" "$CONTAINER_UID" "container runs as the invoking host UID"

# catches: removing `chmod 0775 /data/unibase` from the Dockerfile -> the named
# volume seeds mode 755 owned by 10001 and every other UID fails to write the
# index. Verified against that mutation: the container dies at bootstrap with
# "sqlite3.OperationalError: unable to open database file", so the readiness
# check above trips first. This assertion earns its place by pinning the CAUSE,
# and by catching the latent case where the invoking user happens to BE 10001 --
# then the container works fine here while staying broken for everyone else, and
# no behavioural assertion would notice.
# Also catches a regression to 1777: the volume must be group-writable, never
# world-writable, in an image that advertises a hardened sandbox.
UNIBASE_MODE="$(docker exec metermesh stat -c '%a' /data/unibase 2>/dev/null || echo '-')"
check_eq "775" "$UNIBASE_MODE" "/data/unibase group-writable, not world-writable"

# catches: dropping `group_add: ["10001"]` from docker-compose.yml -> an
# overridden METERMESH_UID loses its route to the gid-10001-owned volume.
CONTAINER_GROUPS="$(docker exec metermesh id -G 2>/dev/null || echo '-')"
if printf '%s\n' $CONTAINER_GROUPS | grep -qx 10001; then
  pass "container holds supplementary gid 10001 (group_add)"
else
  fail "container is missing gid 10001: got '$CONTAINER_GROUPS'"
fi

# Behavioural counterpart to the mode/group pair above: those two pin the
# MECHANISM, this pins the OUTCOME. catches: any future mode/uid/group
# combination that leaves the operator unable to write the index -- including
# ones nobody predicted, which the two exact-value assertions cannot see.
if docker exec metermesh sh -c 'touch /data/unibase/.smoke-probe && rm -f /data/unibase/.smoke-probe' 2>/dev/null; then
  pass "index volume actually writable by UID $CONTAINER_UID"
else
  fail "index volume NOT writable by UID $CONTAINER_UID (mode=$UNIBASE_MODE groups=$CONTAINER_GROUPS)"
fi

# catches: the same chmod removal, at the behavioural level -- no index file.
INDEX_SIZE="$(docker exec metermesh stat -c '%s' /data/unibase/unibase.sqlite3 2>/dev/null || echo 0)"
if [ "${INDEX_SIZE:-0}" -gt 0 ]; then
  pass "unibase index written by UID $CONTAINER_UID ($INDEX_SIZE bytes)"
else
  fail "unibase index was not written (size=${INDEX_SIZE:-0})"
fi

# --------------------------------------------------------------------------
info "Scenario 1: private (0700) sources"

# Negative control for the `user:` override: a container whose UID does NOT own
# the 0700 source dir must be refused. Only meaningful on Linux -- see the SKIP
# message for why. catches (on Linux): removing `user:` from docker-compose.yml
# -> the container runs as 10001, cannot read the user's private ~/.codex, and
# every token assertion above collapses.
if [ "$(uname -s)" = "Linux" ]; then
  FOREIGN_UID=10001
  [ "$UID_VAL" = "10001" ] && FOREIGN_UID=10002
  if docker run --rm -u "$FOREIGN_UID:$FOREIGN_UID" \
       -v "$FIXTURES_HOME/.codex":"$FIXTURES_HOME/.codex":ro \
       --entrypoint sh metermesh:local -c "ls '$FIXTURES_HOME/.codex'" >/dev/null 2>&1; then
    fail "a container running as UID $FOREIGN_UID read a 0700 dir owned by $UID_VAL"
  else
    pass "container with a non-owning UID is denied the 0700 source dir"
  fi
else
  echo "  SKIP (darwin: Docker Desktop's virtiofs remaps bind-mount ownership --"
  echo "        the dir reports owner=<container uid> and a NON-owning UID still"
  echo "        reads a 0700 dir. Verified: uid 10001 read a 0700 dir owned by"
  echo "        uid 501. This assertion is vacuous here; Linux-only. The host-side"
  echo "        mode checks below still run.)"
fi

# catches: the container chmod'ing/chown'ing a source dir it only mounts :ro.
for dir in "${SOURCE_DIRS[@]}"; do
  MODE="$(host_mode "$dir")"
  check_eq "700" "$MODE" "$(basename "$dir") still 0700 after the run"
done

# catches: source mounts becoming writable and allowing add_stat content to
# leak onto the host.
LEAKED=0
for dir in "${ADD_STAT_DIRS[@]}"; do
  if [ -d "$dir" ] && [ -n "$(ls -A "$dir" 2>/dev/null)" ]; then
    fail "host add_stat/ received container writes: $dir"
    LEAKED=1
  fi
done
if [ "$LEAKED" -eq 0 ]; then pass "no container writes reached the host add_stat/ dirs"; fi

# --------------------------------------------------------------------------
info "Result"
if [ "$FAILURES" -eq 0 ]; then
  echo "  PASSED: all assertions held"
else
  echo "  FAILED: $FAILURES assertion(s)"
fi
exit "$FAILURES"
