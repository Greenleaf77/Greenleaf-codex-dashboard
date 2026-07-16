"""Read-only OpenCode SQLite usage adapter for MeterMesh Unibase."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from unibase import Unibase, default_opencode_data_dir, open_source_sqlite_readonly, sanitize_error, stable_id


PARSER_VERSION = 1
OVERLAP_MILLISECONDS = 5 * 60 * 1000
REQUIRED_MESSAGE_COLUMNS = {"id", "session_id", "time_created", "time_updated", "data"}
ALLOWED_READ_TABLES = {"message", "session"}


def resolve_opencode_db(
    cli_value: Path | str | None = None,
    environ: dict[str, str] | None = None,
    data_dir: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    value = cli_value or env.get("OPENCODE_USAGE_DB")
    return Path(value).expanduser() if value else (data_dir or default_opencode_data_dir(env)) / "opencode.db"


def schema_capabilities(conn: sqlite3.Connection) -> dict:
    message_columns = {row[1] for row in conn.execute("pragma table_info(message)")}
    session_columns = {row[1] for row in conn.execute("pragma table_info(session)")}
    try:
        json_supported = bool(conn.execute("select json_valid('{}')").fetchone()[0])
    except sqlite3.DatabaseError:
        json_supported = False
    fingerprint_payload = {
        "message": sorted(message_columns),
        "session": sorted(session_columns),
        "json": json_supported,
        "parser": PARSER_VERSION,
    }
    return {
        **fingerprint_payload,
        "compatible": REQUIRED_MESSAGE_COLUMNS.issubset(message_columns) and json_supported,
        "fingerprint": hashlib.sha256(json.dumps(fingerprint_payload, sort_keys=True).encode()).hexdigest(),
    }


def _authorizer(action: int, table: str | None, _column: str | None, _database: str | None, _trigger: str | None) -> int:
    if action == sqlite3.SQLITE_READ and table and table not in ALLOWED_READ_TABLES and not table.startswith("sqlite_"):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _nonnegative_int(value: object) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0


def _epoch_milliseconds(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 10_000_000_000:
        return number * 1000
    return number


def _event_from_row(row: sqlite3.Row) -> dict | None:
    if row["role"] != "assistant":
        return None
    input_tokens = _nonnegative_int(row["input_tokens"])
    output_tokens = _nonnegative_int(row["output_tokens"])
    reasoning_tokens = _nonnegative_int(row["reasoning_tokens"])
    cache_read_tokens = _nonnegative_int(row["cache_read_tokens"])
    cache_write_tokens = _nonnegative_int(row["cache_write_tokens"])
    if not any((input_tokens, output_tokens, reasoning_tokens, cache_read_tokens, cache_write_tokens)):
        return None
    timestamp_ms = (
        _epoch_milliseconds(row["completed_at"])
        or _epoch_milliseconds(row["created_at"])
        or _epoch_milliseconds(row["time_updated"])
    )
    if timestamp_ms is None:
        return None
    provider_id = str(row["provider_id"] or "opencode").strip() or "opencode"
    model_id = str(row["model_id"] or "(unknown)").strip() or "(unknown)"
    stream_key = stable_id("opencode", "session", row["session_id"])
    message_id = str(row["id"] or "").strip()
    identity = message_id or json.dumps(
        {
            "stream": stream_key,
            "time": timestamp_ms,
            "provider": provider_id,
            "model": model_id,
            "tokens": [input_tokens, output_tokens, reasoning_tokens, cache_read_tokens, cache_write_tokens],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    cost_value = row["cost"]
    try:
        cost = float(cost_value) if cost_value is not None else None
    except (TypeError, ValueError):
        cost = None
    occurred_at = timestamp_ms // 1000
    return {
        "provider": "opencode",
        "event_key": stable_id("opencode", "message", identity),
        "stream_key": stream_key,
        "timestamp_utc": dt.datetime.fromtimestamp(occurred_at, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "occurred_at": occurred_at,
        "model": model_id,
        "native_provider_id": provider_id,
        "semantics": "opencode_recorded",
        "classification": "usage_update",
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cost_usd": cost,
        "cost_kind": "recorded" if cost is not None else "unavailable",
    }


MESSAGE_USAGE_SQL = """
select
    id,
    session_id,
    time_updated,
    json_extract(data, '$.role') role,
    json_extract(data, '$.providerID') provider_id,
    json_extract(data, '$.modelID') model_id,
    json_extract(data, '$.time.completed') completed_at,
    json_extract(data, '$.time.created') created_at,
    json_extract(data, '$.tokens.input') input_tokens,
    json_extract(data, '$.tokens.output') output_tokens,
    json_extract(data, '$.tokens.reasoning') reasoning_tokens,
    json_extract(data, '$.tokens.cache.read') cache_read_tokens,
    json_extract(data, '$.tokens.cache.write') cache_write_tokens,
    json_extract(data, '$.cost') cost
from message
where json_valid(data) and time_updated >= ?
order by time_updated, id
"""

ACTIVE_MESSAGE_IDS_SQL = """
select id, time_updated
from message
where json_valid(data)
  and json_extract(data, '$.role') = 'assistant'
  and (
      max(cast(coalesce(json_extract(data, '$.tokens.input'), 0) as integer), 0) > 0
      or max(cast(coalesce(json_extract(data, '$.tokens.output'), 0) as integer), 0) > 0
      or max(cast(coalesce(json_extract(data, '$.tokens.reasoning'), 0) as integer), 0) > 0
      or max(cast(coalesce(json_extract(data, '$.tokens.cache.read'), 0) as integer), 0) > 0
      or max(cast(coalesce(json_extract(data, '$.tokens.cache.write'), 0) as integer), 0) > 0
  )
  and coalesce(
      json_extract(data, '$.time.completed'),
      json_extract(data, '$.time.created'),
      time_updated
  ) is not null
"""


def import_opencode_source(unibase: Unibase, source: dict, db_override: Path | None = None) -> dict[str, int | float | str | None]:
    source_id = str(source["source_id"])
    source_root = Path(source["root_path"])
    db_path = db_override or (source_root if source_root.name == "opencode.db" else source_root / "opencode.db")
    scan_generation = unibase.begin_source_scan(source_id)
    relative_path = f'file:{stable_id("opencode", "source-file", "opencode.db")}'
    previous = unibase.file_checkpoint(source_id, relative_path)
    try:
        stat = db_path.stat()
        file_identity = f"{stat.st_dev}:{stat.st_ino}"
        with open_source_sqlite_readonly(db_path) as conn:
            conn.set_authorizer(_authorizer)
            conn.execute("begin")
            capabilities = schema_capabilities(conn)
            if not capabilities["compatible"]:
                raise RuntimeError("Unsupported OpenCode message schema")
            cursor_time = 0
            previous_cursor = (0, "")
            if previous and previous.get("change_cursor"):
                try:
                    previous_cursor = tuple(json.loads(previous["change_cursor"]))
                    cursor_time = max(int(previous_cursor[0]) - OVERLAP_MILLISECONDS, 0)
                except (ValueError, TypeError, json.JSONDecodeError):
                    cursor_time = 0
                    previous_cursor = (0, "")
            max_source_time = int(conn.execute("select coalesce(max(time_updated), 0) from message").fetchone()[0])
            active_ids = conn.execute(ACTIVE_MESSAGE_IDS_SQL).fetchall()
            active_key_times = [
                (
                    stable_id("opencode", "message", str(row["id"] or "")),
                    _nonnegative_int(row["time_updated"]),
                )
                for row in active_ids
                if row["id"]
            ]
            existing_keys = unibase.source_event_keys(source_id, "opencode")
            missing_older_event = any(
                event_key not in existing_keys and updated_at < cursor_time
                for event_key, updated_at in active_key_times
            )
            replaced = bool(
                previous
                and (
                    previous.get("content_hash") != file_identity
                    or max_source_time < int(previous_cursor[0])
                    or missing_older_event
                )
            )
            if replaced:
                cursor_time = 0
            rows = conn.execute(MESSAGE_USAGE_SQL, (cursor_time,)).fetchall()
            session_diagnostic = None
            session_columns = set(capabilities["session"])
            aggregate_columns = {
                "tokens_input", "tokens_output", "tokens_reasoning", "tokens_cache_read", "tokens_cache_write", "cost"
            }
            if aggregate_columns.issubset(session_columns):
                session_diagnostic = conn.execute(
                    """
                    select coalesce(sum(tokens_input), 0), coalesce(sum(tokens_output), 0),
                           coalesce(sum(tokens_reasoning), 0), coalesce(sum(tokens_cache_read), 0),
                           coalesce(sum(tokens_cache_write), 0), coalesce(sum(cost), 0)
                    from session
                    """
                ).fetchone()
            conn.commit()

        source_file_id = unibase.upsert_source_file(
            source_id,
            relative_path,
            "opencode_sqlite",
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            scan_generation=scan_generation,
            parser_version=PARSER_VERSION,
            schema_fingerprint=capabilities["fingerprint"],
            content_hash=file_identity,
            change_cursor=previous.get("change_cursor") if previous else None,
        )
        imported = 0
        max_cursor = (0, "")
        parsed_events = []
        for row in rows:
            event = _event_from_row(row)
            row_cursor = (
                _nonnegative_int(row["time_updated"]),
                f'cursor:{stable_id("opencode", "cursor", str(row["id"] or ""))}',
            )
            max_cursor = max(max_cursor, row_cursor)
            if event is None:
                continue
            parsed_events.append(event)
            imported += 1

        all_event_keys = {stable_id("opencode", "message", str(row["id"] or "")) for row in active_ids if row["id"]}
        unibase.replace_source_event_updates(
            source_id, source_file_id, "opencode", parsed_events, all_event_keys, scan_generation
        )
        cursor = (
            max_cursor
            if max_cursor != (0, "")
            else (0, "")
            if replaced
            else tuple(json.loads(previous["change_cursor"]))
            if previous and previous.get("change_cursor")
            else (0, "")
        )
        unibase.upsert_source_file(
            source_id,
            relative_path,
            "opencode_sqlite",
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            scan_generation=scan_generation,
            parser_version=PARSER_VERSION,
            schema_fingerprint=capabilities["fingerprint"],
            content_hash=file_identity,
            change_cursor=json.dumps(cursor),
        )
        source_changed = bool(
            previous is None
            or replaced
            or stat.st_mtime_ns != int(previous["mtime_ns"])
            or any(event_key not in all_event_keys for event_key in existing_keys)
        )
        unibase.reconcile_source_files(
            source_id,
            scan_generation,
            [relative_path],
            rebuild_active=source_changed,
        )
        active = unibase.active_event_rows("opencode")
        message_sums = {
            "input": sum(row["input_tokens"] for row in active),
            "output": sum(row["output_tokens"] for row in active),
            "reasoning": sum(row["reasoning_tokens"] for row in active),
            "cache_read": sum(row["cache_read_tokens"] for row in active),
            "cache_write": sum(row["cache_write_tokens"] for row in active),
        }
        mismatch = None
        if session_diagnostic is not None:
            aggregate = tuple(float(value or 0) for value in session_diagnostic)
            expected = tuple(float(message_sums[key]) for key in ("input", "output", "reasoning", "cache_read", "cache_write"))
            mismatch = any(aggregate[index] != expected[index] for index in range(5))
        return {
            "files": 1,
            "scanned_files": 1,
            "processed_records": imported,
            "new_events": imported,
            "events": len(active),
            "schema_fingerprint": capabilities["fingerprint"],
            "session_aggregate_mismatch": mismatch,
        }
    except Exception as exc:
        unibase.mark_source_error(source_id, sanitize_error(exc) or "OpenCode import failed")
        raise
