"""Incremental Claude Code usage index backed by local JSONL transcripts."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
from pathlib import Path

from unibase import ClosingConnection, Unibase, sanitize_error, stable_id


DEFAULT_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
DEFAULT_CLAUDE_DB = Path.home() / ".claude" / "usage-dashboard.sqlite"
PARSER_VERSION = 3


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
    conn = sqlite3.connect(db_path, timeout=30, factory=ClosingConnection)
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


def _hash_private_id(kind: str, value: object) -> str:
    return stable_id("claude", kind, str(value or ""))


def parse_unibase_event(item: object) -> dict | None:
    """Extract Claude assistant usage without retaining transcript content or raw IDs."""
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
    cache_write_tokens = token_value(usage, "cache_creation_input_tokens")
    cache_read_tokens = token_value(usage, "cache_read_input_tokens")
    output_tokens = token_value(usage, "output_tokens")
    if not any((input_tokens, cache_write_tokens, cache_read_tokens, output_tokens)):
        return None

    native_id = str(item.get("uuid") or message.get("id") or "").strip()
    session_value = item.get("sessionId") or item.get("session_id") or native_id
    stream_key = _hash_private_id("session", session_value)
    timestamp_text, occurred_at, _, _ = timestamp
    if native_id:
        event_key = _hash_private_id("event", native_id)
    else:
        fallback = {
            "timestamp": timestamp_text,
            "model": model,
            "stream": stream_key,
            "input": input_tokens,
            "cache_read": cache_read_tokens,
            "cache_write": cache_write_tokens,
            "output": output_tokens,
        }
        event_key = stable_id("claude", "fallback", json.dumps(fallback, sort_keys=True, separators=(",", ":")))
    return {
        "provider": "claude",
        "event_key": event_key,
        "stream_key": stream_key,
        "timestamp_utc": dt.datetime.fromtimestamp(occurred_at, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "occurred_at": occurred_at,
        "model": model,
        "native_provider_id": "anthropic",
        "semantics": "claude_metadata",
        "classification": "usage_update",
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": 0,
        "cost_usd": None,
        "cost_kind": "unavailable",
    }


def claude_usage_files(root: Path) -> list[Path]:
    projects = root if root.name == "projects" else root / "projects"
    if not projects.is_dir():
        return []
    excluded_parts = {"tool-results", "file-history", "history", "sessions"}
    files = []
    for path in projects.glob("**/*.jsonl"):
        relative = path.relative_to(projects)
        if not path.is_file() or excluded_parts.intersection(relative.parts):
            continue
        if path.name.startswith(".claude.json.backup") or path.name.startswith("meta"):
            continue
        files.append(path)
    return sorted(files)


def _prefix_hash(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    remaining = size
    with path.open("rb") as handle:
        while remaining > 0:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def import_claude_source(
    unibase: Unibase,
    source: dict,
    *,
    force_full_scan: bool = False,
    non_destructive: bool = False,
) -> dict[str, int]:
    source_id = str(source["source_id"])
    root = Path(source["root_path"])
    files = claude_usage_files(root)
    if not root.exists():
        error = FileNotFoundError("Claude source is unavailable")
        unibase.mark_source_error(source_id, error)
        raise error
    scan_generation = unibase.begin_source_scan(source_id)
    scanned_files = 0
    processed_records = 0
    seen_paths: list[str] = []
    dirty_event_keys: set[tuple[str, str]] = set()
    base = root if root.name == "projects" else root / "projects"
    try:
        for path in files:
            relative_path = path.relative_to(base).as_posix()
            file_key = f'file:{stable_id("claude", "source-file", relative_path)}'
            seen_paths.append(file_key)
            stat = path.stat()
            previous = unibase.file_checkpoint(source_id, file_key)
            offset = int(previous["complete_offset"]) if previous else 0
            replaced = bool(
                previous
                and (
                    force_full_scan
                    or int(previous.get("parser_version") or 0) != PARSER_VERSION
                    or stat.st_size < offset
                    or (stat.st_size == int(previous["size"]) and stat.st_mtime_ns != int(previous["mtime_ns"]))
                    or (
                        offset > 0
                        and previous.get("content_hash")
                        and stat.st_mtime_ns != int(previous["mtime_ns"])
                        and _prefix_hash(path, offset) != previous["content_hash"]
                    )
                )
            )
            if replaced:
                offset = 0
            source_file_id = int(previous["source_file_id"]) if previous else unibase.upsert_source_file(
                source_id, file_key, "claude_transcript", size=0, mtime_ns=0,
                complete_offset=0, scan_generation=scan_generation, parser_version=PARSER_VERSION,
            )
            final_offset = offset
            parsed_events = []
            if previous is None or replaced or offset < stat.st_size:
                scanned_files += 1
                with path.open("rb") as handle:
                    handle.seek(offset)
                    while True:
                        line_start = handle.tell()
                        raw_line = handle.readline()
                        if not raw_line:
                            break
                        complete = raw_line.endswith(b"\n")
                        try:
                            item = json.loads(raw_line)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            if not complete:
                                handle.seek(line_start)
                                break
                            continue
                        parsed = parse_unibase_event(item)
                        if parsed:
                            parsed_events.append(parsed)
                            processed_records += 1
                    final_offset = handle.tell()
                if replaced:
                    if non_destructive:
                        dirty_event_keys.update(
                            unibase.add_events(source_id, source_file_id, parsed_events, scan_generation)
                        )
                    else:
                        dirty_event_keys.update(
                            unibase.replace_source_file_events(source_id, source_file_id, parsed_events, scan_generation)
                        )
                else:
                    dirty_event_keys.update(
                        unibase.add_events(source_id, source_file_id, parsed_events, scan_generation)
                    )
            final_stat = path.stat()
            content_hash = _prefix_hash(path, final_offset)
            unibase.upsert_source_file(
                source_id,
                file_key,
                "claude_transcript",
                size=final_stat.st_size,
                mtime_ns=final_stat.st_mtime_ns,
                complete_offset=final_offset,
                content_hash=content_hash,
                scan_generation=scan_generation,
                parser_version=PARSER_VERSION,
            )
        retained_paths = set(seen_paths)
        if non_destructive:
            retained_paths.update(unibase.source_file_keys(source_id))
        unibase.reconcile_source_files(
            source_id,
            scan_generation,
            retained_paths,
            rebuild_active=False,
            dirty_event_keys=dirty_event_keys,
            complete=not non_destructive,
        )
    except Exception as exc:
        unibase.mark_source_error(source_id, sanitize_error(exc) or "Claude import failed")
        raise
    active_count = len([row for row in unibase.active_event_rows("claude")])
    return {
        "files": len(files),
        "scanned_files": scanned_files,
        "processed_records": processed_records,
        "new_events": processed_records,
        "events": active_count,
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
