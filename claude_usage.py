"""Incremental Claude Code usage index backed by local JSONL transcripts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path


DEFAULT_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
DEFAULT_CLAUDE_DB = Path.home() / ".claude" / "usage-dashboard.sqlite"


SCHEMA = """
create table if not exists import_files (
    path text primary key,
    size integer not null,
    mtime_ns integer not null,
    offset integer not null,
    updated_at text not null
);

create table if not exists usage_events (
    event_id text primary key,
    source_path text not null,
    session_id text not null,
    timestamp text not null,
    occurred_at integer not null,
    hour text not null,
    day text not null,
    model text not null,
    input_tokens integer not null,
    cache_creation_input_tokens integer not null,
    cache_read_input_tokens integer not null,
    output_tokens integer not null
);

create index if not exists usage_events_occurred_at on usage_events(occurred_at);
create index if not exists usage_events_day on usage_events(day);
create index if not exists usage_events_source_path on usage_events(source_path);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode = wal")
    conn.execute("pragma busy_timeout = 30000")
    conn.executescript(SCHEMA)
    return conn


def parse_timestamp(value: object) -> tuple[str, int, str, str] | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    local = parsed.astimezone()
    return value, int(parsed.timestamp()), local.strftime("%Y-%m-%d %H:00"), local.date().isoformat()


def token_value(usage: dict, key: str) -> int:
    try:
        return max(int(usage.get(key) or 0), 0)
    except (TypeError, ValueError):
        return 0


def parse_usage_event(item: object, source_path: str, line_offset: int, raw_line: bytes) -> dict | None:
    if not isinstance(item, dict) or item.get("type") != "assistant":
        return None
    message = item.get("message")
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    timestamp = parse_timestamp(item.get("timestamp"))
    if timestamp is None:
        return None
    model = str(message.get("model") or "").strip()
    if not model or model.startswith("<"):
        return None

    input_tokens = token_value(usage, "input_tokens")
    cache_creation_input_tokens = token_value(usage, "cache_creation_input_tokens")
    cache_read_input_tokens = token_value(usage, "cache_read_input_tokens")
    output_tokens = token_value(usage, "output_tokens")
    if not any((input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens)):
        return None

    event_id = str(item.get("uuid") or message.get("id") or "").strip()
    if not event_id:
        digest = hashlib.sha256()
        digest.update(source_path.encode("utf-8"))
        digest.update(str(line_offset).encode("ascii"))
        digest.update(raw_line)
        event_id = digest.hexdigest()
    session_id = str(item.get("sessionId") or event_id)
    timestamp_text, occurred_at, hour, day = timestamp
    return {
        "event_id": event_id,
        "source_path": source_path,
        "session_id": session_id,
        "timestamp": timestamp_text,
        "occurred_at": occurred_at,
        "hour": hour,
        "day": day,
        "model": model,
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": cache_creation_input_tokens,
        "cache_read_input_tokens": cache_read_input_tokens,
        "output_tokens": output_tokens,
    }


def import_file(conn: sqlite3.Connection, path: Path, source_path: str, offset: int) -> tuple[int, int]:
    imported = 0
    with path.open("rb") as handle:
        handle.seek(offset)
        while True:
            line_start = handle.tell()
            raw_line = handle.readline()
            if not raw_line:
                break
            complete_line = raw_line.endswith(b"\n")
            try:
                item = json.loads(raw_line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                if not complete_line:
                    handle.seek(line_start)
                    break
                continue
            event = parse_usage_event(item, source_path, line_start, raw_line)
            if event is None:
                continue
            conn.execute(
                """
                insert into usage_events (
                    event_id, source_path, session_id, timestamp, occurred_at, hour, day, model,
                    input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens
                ) values (
                    :event_id, :source_path, :session_id, :timestamp, :occurred_at, :hour, :day, :model,
                    :input_tokens, :cache_creation_input_tokens, :cache_read_input_tokens, :output_tokens
                )
                on conflict(event_id) do update set
                    source_path = excluded.source_path,
                    session_id = excluded.session_id,
                    timestamp = excluded.timestamp,
                    occurred_at = excluded.occurred_at,
                    hour = excluded.hour,
                    day = excluded.day,
                    model = excluded.model,
                    input_tokens = excluded.input_tokens,
                    cache_creation_input_tokens = excluded.cache_creation_input_tokens,
                    cache_read_input_tokens = excluded.cache_read_input_tokens,
                    output_tokens = excluded.output_tokens
                """,
                event,
            )
            imported += 1
        return handle.tell(), imported


def index_claude_usage(projects_path: Path, db_path: Path) -> dict[str, int]:
    projects_path = projects_path.expanduser()
    db_path = db_path.expanduser()
    if not projects_path.exists():
        raise FileNotFoundError(f"Claude projects directory not found: {projects_path}")

    files = sorted(path for path in projects_path.rglob("*.jsonl") if path.is_file())
    relative_paths = {path.relative_to(projects_path).as_posix(): path for path in files}
    scanned_files = 0
    processed_records = 0

    with connect(db_path) as conn:
        conn.execute("begin immediate")
        existing = {row["path"]: row for row in conn.execute("select path, size, mtime_ns, offset from import_files")}
        missing_paths = set(existing) - set(relative_paths)
        for source_path in missing_paths:
            conn.execute("delete from usage_events where source_path = ?", (source_path,))
            conn.execute("delete from import_files where path = ?", (source_path,))

        before_count = int(conn.execute("select count(*) from usage_events").fetchone()[0])
        for source_path, path in relative_paths.items():
            stat = path.stat()
            previous = existing.get(source_path)
            offset = int(previous["offset"]) if previous else 0
            replaced = bool(
                previous
                and (
                    stat.st_size < offset
                    or (stat.st_size == int(previous["size"]) and stat.st_mtime_ns != int(previous["mtime_ns"]))
                )
            )
            if replaced:
                conn.execute("delete from usage_events where source_path = ?", (source_path,))
                offset = 0
            final_offset = offset
            if offset < stat.st_size or replaced or previous is None:
                scanned_files += 1
                final_offset, imported = import_file(conn, path, source_path, offset)
                processed_records += imported
            final_stat = path.stat()
            conn.execute(
                """
                insert into import_files(path, size, mtime_ns, offset, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(path) do update set
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    offset = excluded.offset,
                    updated_at = excluded.updated_at
                """,
                (
                    source_path,
                    final_stat.st_size,
                    final_stat.st_mtime_ns,
                    final_offset,
                    dt.datetime.now(dt.timezone.utc).isoformat(),
                ),
            )
        after_count = int(conn.execute("select count(*) from usage_events").fetchone()[0])

    return {
        "files": len(files),
        "scanned_files": scanned_files,
        "processed_records": processed_records,
        "new_events": max(after_count - before_count, 0),
        "events": after_count,
    }


def load_claude_events(db_path: Path, start_ts: int | None = None) -> list[dict]:
    db_path = db_path.expanduser()
    if not db_path.exists():
        return []
    with connect(db_path) as conn:
        sql = "select * from usage_events"
        params: tuple[int, ...] = ()
        if start_ts is not None:
            sql += " where occurred_at >= ?"
            params = (start_ts,)
        sql += " order by occurred_at, event_id"
        rows = conn.execute(sql, params).fetchall()

    events = []
    for row in rows:
        cached_input_tokens = row["cache_creation_input_tokens"] + row["cache_read_input_tokens"]
        raw_input_tokens = row["input_tokens"] + cached_input_tokens
        events.append(
            {
                "thread_id": row["session_id"],
                "timestamp": row["timestamp"],
                "hour": row["hour"],
                "day": row["day"],
                "model": row["model"],
                "source": "claude_jsonl",
                "classification": "usage_update",
                "response_id": row["event_id"],
                "input_tokens": row["input_tokens"],
                "cache_creation_input_tokens": row["cache_creation_input_tokens"],
                "cache_read_input_tokens": row["cache_read_input_tokens"],
                "cached_input_tokens": cached_input_tokens,
                "raw_input_tokens": raw_input_tokens,
                "output_tokens": row["output_tokens"],
                "reasoning_output_tokens": 0,
                "total_tokens": row["input_tokens"] + row["output_tokens"],
                "total_with_cached_tokens": raw_input_tokens + row["output_tokens"],
            }
        )
    return events
