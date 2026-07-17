#!/usr/bin/env python3
"""Generate the binary Docker smoke-test fixtures that cannot be committed.

state_5.sqlite stores host-ABSOLUTE rollout paths, so it only becomes valid once
we know where this repo is checked out. Committing a pre-baked copy would bake in
somebody else's absolute path. opencode.db is generated for the same reason it is
not committed: it is a binary artifact with no reason to live in git.

Usage: make_fixtures.py <fixtures-home>
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# Kept in sync with tests/docker/smoke.sh, which asserts on these exact strings.
SESSIONS_ROLLOUT = (
    ".codex/sessions/2026/01/01/"
    "rollout-2026-01-01T00-00-00-11111111-1111-4111-8111-111111111111.jsonl"
)
# Deliberately outside <home>/.codex/sessions/. codex_usage.codex_usage_files()
# only globs root/sessions/**, so this rollout is reachable ONLY by resolving the
# absolute rollout_path held in state_5.sqlite -- which is exactly what the
# same-path bind mount exists to make work.
ARCHIVE_ROLLOUT = (
    ".codex/archive/sessions/"
    "rollout-2026-01-02T00-00-00-22222222-2222-4222-8222-222222222222.jsonl"
)

# Differs from the "smoke-codex-meta-model" recorded in the rollout JSONL's
# session_meta. import_codex_source() prefers the state-db model and falls back to
# the JSONL model when the absolute path fails to resolve, so the indexed model
# name tells us which lookup actually won.
STATE_MODEL = "smoke-codex-state-model"


def write_codex_state(home: Path) -> Path:
    state_path = home / ".codex" / "state_5.sqlite"
    state_path.unlink(missing_ok=True)
    rows = [
        ("thread-sessions", str(home / SESSIONS_ROLLOUT), STATE_MODEL),
        ("thread-archive", str(home / ARCHIVE_ROLLOUT), STATE_MODEL),
    ]
    for _, rollout_path, _ in rows:
        if not Path(rollout_path).is_file():
            raise SystemExit(f"fixture rollout missing: {rollout_path}")
    with sqlite3.connect(state_path) as conn:
        conn.execute("create table threads (id text primary key, rollout_path text, model text)")
        conn.executemany("insert into threads values (?, ?, ?)", rows)
    return state_path


def write_opencode_db(home: Path) -> Path:
    db_path = home / ".local" / "share" / "opencode" / "opencode.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    # Columns per opencode_usage.REQUIRED_MESSAGE_COLUMNS; `session` is read only
    # for optional aggregate diagnostics but must exist for pragma table_info().
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table session (id text primary key, time_created integer)")
        conn.execute(
            "create table message ("
            "id text primary key, session_id text, time_created integer,"
            " time_updated integer, data text)"
        )
        conn.execute(
            "insert into session values ('smoke-opencode-session', 1767398400000)"
        )
        conn.execute(
            "insert into message values (?, ?, ?, ?, ?)",
            (
                "smoke-opencode-message",
                "smoke-opencode-session",
                1767398400000,
                1767398400000,
                '{"role": "assistant", "providerID": "smoke-provider",'
                ' "modelID": "smoke-opencode-model",'
                ' "time": {"created": 1767398400000, "completed": 1767398405000},'
                ' "tokens": {"input": 5001, "output": 5002, "reasoning": 0,'
                ' "cache": {"read": 0, "write": 0}}, "cost": 0.5}',
            ),
        )
    return db_path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} <fixtures-home>")
    # Preserve the exact host path used as the container mount target. Resolving
    # macOS /var to /private/var would write state paths that do not exist in the
    # container even though both names refer to the same host directory.
    home = Path(sys.argv[1]).absolute()
    if not home.is_dir():
        raise SystemExit(f"fixtures home does not exist: {home}")
    print(f"generated {write_codex_state(home)}")
    print(f"generated {write_opencode_db(home)}")


if __name__ == "__main__":
    main()
