"""Codex rollout discovery, telemetry reconstruction, and Unibase ingestion."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from unibase import Unibase, open_source_sqlite_readonly, sanitize_error, stable_id


PARSER_VERSION = 2
AUTO_REVIEW_MODEL = "codex-auto-review"
USAGE_COMPONENTS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
ROLLOUT_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
ROLLOUT_FILENAME = re.compile(r"^rollout-.*\.jsonl$")


def parse_usage_components(value: object, *, cumulative: bool = False) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    if cumulative and any(key not in value for key in USAGE_COMPONENTS[:3]):
        return None
    try:
        usage = {key: int(value.get(key) or 0) for key in USAGE_COMPONENTS}
    except (TypeError, ValueError):
        return None
    if any(component < 0 for component in usage.values()):
        return None
    return usage


def usage_has_tokens(usage: dict[str, int] | None) -> bool:
    return bool(usage and any(usage[key] > 0 for key in USAGE_COMPONENTS))


def is_model_output_item(item_type: str | None, payload: dict) -> bool:
    if item_type == "event_msg" and payload.get("type") in {"agent_message", "agent_reasoning"}:
        return True
    if item_type != "response_item":
        return False
    payload_type = payload.get("type")
    if payload_type == "reasoning":
        return True
    if payload_type == "message":
        return payload.get("role") == "assistant"
    return isinstance(payload_type, str) and payload_type.endswith("_call") and not payload_type.endswith("_call_output")


def usage_event(
    stream_key: str,
    model: str,
    timestamp: str,
    usage: dict[str, int],
    source: str,
    classification: str,
    response_id: str | None = None,
) -> dict:
    raw_input = usage["input_tokens"]
    cache_read = usage["cached_input_tokens"]
    occurred_at = int(dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
    return {
        "stream_key": stream_key,
        "timestamp_utc": dt.datetime.fromtimestamp(occurred_at, dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "occurred_at": occurred_at,
        "model": model,
        "source": source,
        "classification": classification,
        "response_id": response_id,
        "input_tokens": max(raw_input - cache_read, 0),
        "cache_read_tokens": cache_read,
        "cache_write_tokens": 0,
        "output_tokens": usage["output_tokens"],
        "reasoning_tokens": usage["reasoning_output_tokens"],
    }


def scan_rollout_telemetry(rollout_path: Path, stream_key: str, model: str) -> dict[str, list[dict]]:
    token_records: list[dict] = []
    exact_records: list[dict] = []
    model_output_since_token = False
    with rollout_path.open(encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, 1):
            if not any(marker in line for marker in ('"token_count"', '"raw_response_completed"', '"response_item"', '"agent_message"', '"agent_reasoning"')):
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = item.get("payload") or {}
            if not isinstance(payload, dict):
                continue
            item_type = item.get("type")
            payload_type = payload.get("type")
            if is_model_output_item(item_type, payload):
                model_output_since_token = True
                continue
            if payload_type == "raw_response_completed":
                timestamp = item.get("timestamp")
                parsed = parse_usage_components(payload.get("token_usage"))
                if timestamp and parsed and usage_has_tokens(parsed):
                    exact_records.append({"line_number": line_number, "timestamp": timestamp, "response_id": str(payload.get("response_id") or ""), "usage": parsed})
                model_output_since_token = True
                continue
            if payload_type != "token_count":
                continue
            timestamp = item.get("timestamp")
            if not timestamp:
                model_output_since_token = False
                continue
            info = payload.get("info") or {}
            token_records.append({
                "line_number": line_number,
                "timestamp": timestamp,
                "last": parse_usage_components(info.get("last_token_usage")),
                "cumulative": parse_usage_components(info.get("total_token_usage"), cumulative=True),
                "model_output": model_output_since_token,
            })
            model_output_since_token = False

    unique_exact = []
    seen_response_ids = set()
    for record in exact_records:
        response_id = record["response_id"]
        if response_id and response_id in seen_response_ids:
            continue
        if response_id:
            seen_response_ids.add(response_id)
        unique_exact.append(record)
    covered_lines = set()
    token_index = 0
    for record in unique_exact:
        while token_index < len(token_records) and token_records[token_index]["line_number"] < record["line_number"]:
            token_index += 1
        if token_index < len(token_records):
            covered_lines.add(token_records[token_index]["line_number"])
            token_index += 1

    previous = None
    token_events = []
    fallback_events = []
    for record in token_records:
        current = record["cumulative"]
        last = record["last"]
        contribution = None
        if current is None:
            classification = "unverifiable_event"
            if record["model_output"] and usage_has_tokens(last):
                contribution = last
        elif previous is None:
            if record["model_output"] and usage_has_tokens(last):
                classification = "usage_update"
                contribution = last
            else:
                classification = "baseline_event"
            previous = current
        elif all(current[key] == previous[key] for key in USAGE_COMPONENTS):
            classification = "replayed_event"
        elif all(current[key] >= previous[key] for key in USAGE_COMPONENTS):
            classification = "usage_update"
            contribution = {key: current[key] - previous[key] for key in USAGE_COMPONENTS}
            previous = current
        else:
            classification = "counter_reset"
            if record["model_output"] and usage_has_tokens(last):
                contribution = last
            previous = current
        raw = last or {key: 0 for key in USAGE_COMPONENTS}
        token_events.append(usage_event(stream_key, model, record["timestamp"], raw, "reported", classification))
        if contribution and usage_has_tokens(contribution) and record["line_number"] not in covered_lines:
            fallback_events.append(usage_event(stream_key, model, record["timestamp"], contribution, "fallback", classification))

    exact_events = [
        usage_event(stream_key, model, record["timestamp"], record["usage"], "exact", "usage_update", record["response_id"] or None)
        for record in unique_exact
    ]
    return {"usage_events": sorted(fallback_events + exact_events, key=lambda item: item["timestamp_utc"]), "token_events": token_events}


def codex_usage_files(root: Path) -> list[Path]:
    sessions = root / "sessions"
    return sorted(path for path in sessions.glob("**/rollout-*.jsonl") if path.is_file()) if sessions.is_dir() else []


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rollout_metadata(path: Path, content_hash: str) -> tuple[str, str]:
    session_id = None
    model = None
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for _ in range(80):
            line = handle.readline()
            if not line:
                break
            if "session_meta" not in line and '"model"' not in line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = item.get("payload") or {}
            if payload.get("type") == "session_meta" or item.get("type") == "session_meta":
                session_id = payload.get("id") or payload.get("session_id")
                model = payload.get("model") or model
            model = payload.get("model") or model
            if session_id and model:
                break
    if not session_id:
        match = ROLLOUT_UUID.search(str(path).replace("\\", "/"))
        session_id = match.group(0) if match else content_hash
    return stable_id("codex", "stream", session_id), str(model or "(unknown)")


def _validated_state_rollout(value: object) -> tuple[Path, Path, str] | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts or not ROLLOUT_FILENAME.fullmatch(path.name):
        return None
    session_indexes = [index for index, part in enumerate(path.parts) if part == "sessions"]
    if not session_indexes:
        return None
    try:
        sessions_root = Path(*path.parts[: session_indexes[-1] + 1]).resolve()
        resolved = path.resolve()
        relative = resolved.relative_to(sessions_root).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved, sessions_root, relative


def _state_rollouts(state_path: Path) -> tuple[dict[Path, str], bool]:
    if not state_path.is_file():
        return {}, False
    try:
        with open_source_sqlite_readonly(state_path) as conn:
            columns = {row[1] for row in conn.execute("pragma table_info(threads)")}
            if "rollout_path" not in columns:
                return {}, False
            model_sql = "model" if "model" in columns else "null"
            rows = conn.execute(
                f"select rollout_path, {model_sql} model from threads where rollout_path != ''"
            ).fetchall()
    except Exception:
        return {}, False

    rollouts: dict[Path, str] = {}
    complete = True
    for row in rows:
        validated = _validated_state_rollout(row["rollout_path"])
        if validated is None:
            complete = False
            continue
        path, _, _ = validated
        rollouts[path] = str(row["model"] or "(unknown)")
    return rollouts, complete


def import_codex_source(
    unibase: Unibase,
    source: dict,
    *,
    ignore_auto_review: bool = False,
    state_path: Path | None = None,
    require_state_inventory: bool = False,
) -> dict[str, int]:
    source_id = str(source["source_id"])
    root = Path(source["root_path"])
    if not root.exists():
        error = FileNotFoundError("Codex source is unavailable")
        unibase.mark_source_error(source_id, error)
        raise error
    default_files = codex_usage_files(root)
    is_live = source.get("kind") == "live"
    state_rollouts, state_inventory_complete = _state_rollouts(
        state_path or root / "state_5.sqlite"
    )
    backup_models = {path.name: model for path, model in state_rollouts.items()} if not is_live else {}

    inventory: list[tuple[Path, str]] = []
    default_paths = set()
    for path in default_files:
        resolved = path.resolve()
        default_paths.add(resolved)
        relative = path.relative_to(root).as_posix()
        inventory.append((path, f'file:{stable_id("codex", "source-file", relative)}'))
    for path in (sorted(state_rollouts) if is_live else []):
        if path in default_paths:
            continue
        validated = _validated_state_rollout(str(path))
        if validated is None:
            state_inventory_complete = False
            continue
        resolved, sessions_root, relative = validated
        root_key = stable_id("codex", "rollout-root", str(sessions_root))
        file_key = stable_id("codex", "source-file", relative)
        external_key = f"external:{root_key}:{file_key}"
        if not resolved.is_file():
            state_inventory_complete = False
            continue
        inventory.append((resolved, external_key))

    if require_state_inventory and not state_inventory_complete:
        raise RuntimeError("Codex state inventory is unavailable or incomplete")

    scan_generation = unibase.begin_source_scan(source_id)
    seen_paths = []
    parsed_files = 0
    imported = 0
    try:
        for path, file_key in inventory:
            seen_paths.append(file_key)
            stat = path.stat()
            content_hash = _file_hash(path)
            previous = unibase.file_checkpoint(source_id, file_key)
            unchanged = bool(previous and previous.get("content_hash") == content_hash and int(previous["size"]) == stat.st_size)
            if unchanged:
                continue
            unibase.register_content_blob(content_hash, stat.st_size, "codex", PARSER_VERSION)
            source_file_id = int(previous["source_file_id"]) if previous else unibase.upsert_source_file(
                source_id, file_key, "codex_rollout", size=0, mtime_ns=0, content_hash=None,
                scan_generation=scan_generation, parser_version=PARSER_VERSION,
            )
            stream_key, metadata_model = rollout_metadata(path, content_hash)
            model = state_rollouts.get(path.resolve(), backup_models.get(path.name, metadata_model))
            telemetry = {"usage_events": []} if ignore_auto_review and model == AUTO_REVIEW_MODEL else scan_rollout_telemetry(path, stream_key, model)
            ordinals: dict[tuple[str, str, str], int] = {}
            parsed_events = []
            for item in telemetry["usage_events"]:
                ordinal_key = (item["timestamp_utc"], item["source"], item["classification"])
                ordinal = ordinals.get(ordinal_key, 0)
                ordinals[ordinal_key] = ordinal + 1
                response_id = item.get("response_id")
                if response_id:
                    event_key = stable_id("codex", "response", response_id)
                else:
                    event_key = stable_id("codex", "record", stream_key, *ordinal_key, ordinal)
                parsed_events.append({
                    "provider": "codex",
                    "event_key": event_key,
                    "stream_key": stream_key,
                    "timestamp_utc": item["timestamp_utc"],
                    "occurred_at": item["occurred_at"],
                    "model": model,
                    "native_provider_id": "openai",
                    "semantics": "exact" if item["source"] == "exact" else "cumulative_fallback",
                    "classification": item["classification"],
                    "input_tokens": item["input_tokens"],
                    "cache_read_tokens": item["cache_read_tokens"],
                    "cache_write_tokens": 0,
                    "output_tokens": item["output_tokens"],
                    "reasoning_tokens": item["reasoning_tokens"],
                    "cost_usd": None,
                    "cost_kind": "unavailable",
                })
                imported += 1
            unibase.replace_source_file_events(source_id, source_file_id, parsed_events, scan_generation)
            unibase.upsert_source_file(
                source_id, file_key, "codex_rollout", size=stat.st_size, mtime_ns=stat.st_mtime_ns,
                complete_offset=stat.st_size, content_hash=content_hash, scan_generation=scan_generation,
                parser_version=PARSER_VERSION,
            )
            parsed_files += 1
        if is_live and not state_inventory_complete:
            seen_paths.extend(
                key for key in unibase.source_file_keys(source_id, file_kind="codex_rollout")
                if key.startswith("external:")
            )
        unibase.reconcile_source_files(
            source_id,
            scan_generation,
            seen_paths,
            rebuild_active=parsed_files > 0,
        )
        if is_live and not state_inventory_complete:
            unibase.mark_source_error(source_id, "Codex state inventory is incomplete; retained committed data")
        return {
            "files": len(set(seen_paths)),
            "scanned_files": parsed_files,
            "processed_records": imported,
            "new_events": imported,
            "events": len(unibase.active_event_rows("codex")),
        }
    except Exception as exc:
        unibase.mark_source_error(source_id, sanitize_error(exc) or "Codex import failed")
        raise
