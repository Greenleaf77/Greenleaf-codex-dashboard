#!/usr/bin/env python3
"""Local Codex and Claude Code usage dashboard."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from claude_usage import DEFAULT_CLAUDE_DB, DEFAULT_CLAUDE_PROJECTS, index_claude_usage, load_claude_events


DEFAULT_DB = Path.home() / ".codex" / "state_5.sqlite"
PROVIDERS = {"codex", "claude"}
RANGES = {"all", "30d", "7d", "1d", "custom"}
CHART_RANGES = {"all", "1y", "6m", "90d", "30d", "custom"}
AUTO_REVIEW_MODEL = "codex-auto-review"
PRICING_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
PRICING_CACHE_SECONDS = 600
PRICING_CACHE: dict[str, object] = {"loaded_at": 0.0, "pricing": None}
FALLBACK_PRICING = {
    "gpt-5.5": {
        "input_cost_per_token": 0.000005,
        "cache_read_input_token_cost": 0.0000005,
        "output_cost_per_token": 0.00003,
    },
    "gpt-5.4": {
        "input_cost_per_token": 0.0000025,
        "cache_read_input_token_cost": 0.00000025,
        "output_cost_per_token": 0.000015,
    },
    "gpt-5.3-codex": {
        "input_cost_per_token": 0.00000175,
        "cache_read_input_token_cost": 0.000000175,
        "output_cost_per_token": 0.000014,
    },
    "gpt-5.2-codex": {
        "input_cost_per_token": 0.00000175,
        "cache_read_input_token_cost": 0.000000175,
        "output_cost_per_token": 0.000014,
    },
    "gpt-5.6-sol": {
        "input_cost_per_token": 0.000005,
        "cache_creation_input_token_cost": 0.00000625,
        "cache_read_input_token_cost": 0.0000005,
        "output_cost_per_token": 0.00003,
    },
    "claude-sonnet-5": {
        "input_cost_per_token": 0.000002,
        "cache_creation_input_token_cost": 0.0000025,
        "cache_read_input_token_cost": 0.0000002,
        "output_cost_per_token": 0.00001,
    },
    "claude-fable-5": {
        "input_cost_per_token": 0.00001,
        "cache_creation_input_token_cost": 0.0000125,
        "cache_read_input_token_cost": 0.000001,
        "output_cost_per_token": 0.00005,
    },
    "claude-opus-4-8": {
        "input_cost_per_token": 0.000005,
        "cache_creation_input_token_cost": 0.00000625,
        "cache_read_input_token_cost": 0.0000005,
        "output_cost_per_token": 0.000025,
    },
    "claude-sonnet-4-6": {
        "input_cost_per_token": 0.000003,
        "cache_creation_input_token_cost": 0.00000375,
        "cache_read_input_token_cost": 0.0000003,
        "output_cost_per_token": 0.000015,
    },
}


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Codex state database not found: {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_int(value: int | float | None) -> str:
    return f"{int(value or 0):,}"


def fmt_short(value: int | float | None) -> str:
    value = int(value or 0)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def fmt_usd(value: int | float | None) -> str:
    return f"${float(value or 0):,.2f}"


def iso_from_unix(value: int | None) -> str:
    if value is None:
        return "-"
    return dt.datetime.fromtimestamp(value).date().isoformat()


def day_from_iso_timestamp(value: str) -> str:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().date().isoformat()


def normalize_provider(provider: str | None) -> str:
    return provider if provider in PROVIDERS else "codex"


def normalize_range(range_name: str | None) -> str:
    return range_name if range_name in RANGES else "all"


def normalize_chart_range(range_name: str | None) -> str:
    return range_name if range_name in CHART_RANGES else "30d"


def parse_iso_day(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def day_start_timestamp(value: dt.date) -> int:
    return int(dt.datetime.combine(value, dt.time.min).timestamp())


def days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = dt.date(year + 1, 1, 1)
    else:
        next_month = dt.date(year, month + 1, 1)
    return (next_month - dt.timedelta(days=1)).day


def add_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, days_in_month(year, month))
    return dt.date(year, month, day)


def parse_bool_flag(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_pricing() -> dict:
    now = dt.datetime.now().timestamp()
    cached = PRICING_CACHE.get("pricing")
    loaded_at = float(PRICING_CACHE.get("loaded_at") or 0)
    if isinstance(cached, dict) and now - loaded_at < PRICING_CACHE_SECONDS:
        return cached

    try:
        request = Request(PRICING_URL, headers={"User-Agent": "codex-usage-dashboard"})
        with urlopen(request, timeout=2.5) as response:
            live_pricing = json.loads(response.read().decode("utf-8"))
        pricing = {
            "source": "LiteLLM live",
            "url": PRICING_URL,
            "loaded_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "models": live_pricing,
            "fallback": FALLBACK_PRICING,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        pricing = {
            "source": "bundled fallback",
            "url": PRICING_URL,
            "loaded_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "models": FALLBACK_PRICING,
            "fallback": FALLBACK_PRICING,
            "error": exc.__class__.__name__,
        }

    PRICING_CACHE["loaded_at"] = now
    PRICING_CACHE["pricing"] = pricing
    return pricing


def model_price_key(model: str, pricing_models: dict) -> str | None:
    base_model = model
    for prefix in ("openai/", "anthropic/"):
        if base_model.startswith(prefix):
            base_model = base_model.removeprefix(prefix)
            break
    candidates = [model, base_model, f"openai/{base_model}", f"anthropic/{base_model}"]
    for candidate in candidates:
        if candidate in pricing_models:
            return candidate
    return None


def token_cost_usd(event: dict, pricing: dict) -> tuple[float, str | None]:
    models = pricing["models"]
    fallback = pricing["fallback"]
    price_key = model_price_key(event["model"], models)
    price_source = models
    if price_key is None:
        price_key = model_price_key(event["model"], fallback)
        price_source = fallback
    if price_key is None:
        return 0.0, event["model"]

    model_price = price_source[price_key]
    input_price = float(model_price.get("input_cost_per_token") or 0)
    cache_creation_price = model_price.get("cache_creation_input_token_cost")
    if cache_creation_price is None:
        cache_creation_price = input_price
    cache_read_price = model_price.get("cache_read_input_token_cost")
    if cache_read_price is None:
        cache_read_price = input_price
    output_price = float(model_price.get("output_cost_per_token") or 0)
    cache_creation_tokens = int(event.get("cache_creation_input_tokens") or 0)
    cache_read_tokens = event.get("cache_read_input_tokens")
    if cache_read_tokens is None:
        cache_read_tokens = max(int(event["cached_input_tokens"]) - cache_creation_tokens, 0)
    cost = (
        event["input_tokens"] * input_price
        + cache_creation_tokens * float(cache_creation_price)
        + int(cache_read_tokens) * float(cache_read_price)
        + event["output_tokens"] * output_price
    )
    return cost, None


def resolve_range(
    range_name: str | None,
    start_day: str | None = None,
    end_day: str | None = None,
    ignore_auto_review: bool = False,
) -> dict[str, str | int | bool | None]:
    range_name = normalize_range(range_name)
    today = dt.date.today()
    start_date: dt.date | None = None
    end_date: dt.date | None = None

    if range_name == "1d":
        start_date = today
        end_date = today
    elif range_name == "7d":
        start_date = today - dt.timedelta(days=6)
        end_date = today
    elif range_name == "30d":
        start_date = today - dt.timedelta(days=29)
        end_date = today
    elif range_name == "custom":
        start_date = parse_iso_day(start_day) or today
        end_date = parse_iso_day(end_day) or start_date
        if start_date > end_date:
            start_date, end_date = end_date, start_date

    return {
        "range": range_name,
        "start_day": start_date.isoformat() if start_date else None,
        "end_day": end_date.isoformat() if end_date else None,
        "start_ts": day_start_timestamp(start_date) if start_date else None,
        "ignore_auto_review": ignore_auto_review,
    }


def resolve_chart_range(
    range_name: str | None,
    start_day: str | None = None,
    end_day: str | None = None,
    ignore_auto_review: bool = False,
) -> dict[str, str | int | bool | None]:
    range_name = normalize_chart_range(range_name)
    today = dt.date.today()
    start_date: dt.date | None = None
    end_date: dt.date | None = None

    if range_name == "30d":
        start_date = today - dt.timedelta(days=29)
        end_date = today
    elif range_name == "90d":
        start_date = today - dt.timedelta(days=89)
        end_date = today
    elif range_name == "6m":
        start_date = add_months(today, -6) + dt.timedelta(days=1)
        end_date = today
    elif range_name == "1y":
        start_date = today - dt.timedelta(days=364)
        end_date = today
    elif range_name == "custom":
        start_date = parse_iso_day(start_day) or (today - dt.timedelta(days=29))
        end_date = parse_iso_day(end_day) or today
        if start_date > end_date:
            start_date, end_date = end_date, start_date

    return {
        "range": range_name,
        "start_day": start_date.isoformat() if start_date else None,
        "end_day": end_date.isoformat() if end_date else None,
        "start_ts": day_start_timestamp(start_date) if start_date else None,
        "ignore_auto_review": ignore_auto_review,
    }


def longest_streak(days: set[str]) -> int:
    if not days:
        return 0
    parsed = sorted(dt.date.fromisoformat(day) for day in days)
    best = current = 1
    for prev, day in zip(parsed, parsed[1:]):
        if day == prev + dt.timedelta(days=1):
            current += 1
        else:
            current = 1
        best = max(best, current)
    return best


def current_streak(days: set[str]) -> int:
    today = dt.date.today()
    current = 0
    cursor = today
    while cursor.isoformat() in days:
        current += 1
        cursor -= dt.timedelta(days=1)
    return current


USAGE_COMPONENTS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


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


def local_hour_from_iso_timestamp(value: str) -> str:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    return parsed.strftime("%Y-%m-%d %H:00")


def usage_event(
    thread_id: str,
    model: str,
    timestamp: str,
    usage: dict[str, int],
    source: str,
    classification: str,
    response_id: str | None = None,
) -> dict:
    raw_input_tokens = usage["input_tokens"]
    cached_input_tokens = usage["cached_input_tokens"]
    output_tokens = usage["output_tokens"]
    billable_input_tokens = max(raw_input_tokens - cached_input_tokens, 0)
    return {
        "thread_id": thread_id,
        "timestamp": timestamp,
        "hour": local_hour_from_iso_timestamp(timestamp),
        "day": day_from_iso_timestamp(timestamp),
        "model": model,
        "source": source,
        "classification": classification,
        "response_id": response_id,
        "input_tokens": billable_input_tokens,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": cached_input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "raw_input_tokens": raw_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": usage["reasoning_output_tokens"],
        "total_tokens": billable_input_tokens + output_tokens,
        "total_with_cached_tokens": raw_input_tokens + output_tokens,
    }


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


def scan_rollout_telemetry(rollout_path: Path, thread_id: str, model: str) -> dict[str, list[dict]]:
    token_records: list[dict] = []
    exact_records: list[dict] = []
    model_output_since_token = False

    with rollout_path.open(encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, 1):
            if not any(
                marker in line
                for marker in ('"token_count"', '"raw_response_completed"', '"response_item"', '"agent_message"', '"agent_reasoning"')
            ):
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
                parsed_usage = parse_usage_components(payload.get("token_usage"))
                if timestamp and parsed_usage and usage_has_tokens(parsed_usage):
                    exact_records.append(
                        {
                            "line_number": line_number,
                            "timestamp": timestamp,
                            "response_id": str(payload.get("response_id") or ""),
                            "usage": parsed_usage,
                        }
                    )
                model_output_since_token = True
                continue
            if payload_type != "token_count":
                continue
            timestamp = item.get("timestamp")
            if not timestamp:
                model_output_since_token = False
                continue
            info = payload.get("info") or {}
            token_records.append(
                {
                    "line_number": line_number,
                    "timestamp": timestamp,
                    "last": parse_usage_components(info.get("last_token_usage")),
                    "cumulative": parse_usage_components(info.get("total_token_usage"), cumulative=True),
                    "model_output": model_output_since_token,
                }
            )
            model_output_since_token = False

    unique_exact_records: list[dict] = []
    seen_response_ids: set[str] = set()
    for record in exact_records:
        response_id = record["response_id"]
        if response_id and response_id in seen_response_ids:
            continue
        if response_id:
            seen_response_ids.add(response_id)
        unique_exact_records.append(record)

    covered_token_lines: set[int] = set()
    token_index = 0
    for record in unique_exact_records:
        while token_index < len(token_records) and token_records[token_index]["line_number"] < record["line_number"]:
            token_index += 1
        if token_index < len(token_records):
            covered_token_lines.add(token_records[token_index]["line_number"])
            token_index += 1

    previous_cumulative: dict[str, int] | None = None
    token_events: list[dict] = []
    fallback_usage_events: list[dict] = []

    for record in token_records:
        current = record["cumulative"]
        last = record["last"]
        contribution: dict[str, int] | None = None
        if current is None:
            classification = "unverifiable_event"
            if record["model_output"] and usage_has_tokens(last):
                contribution = last
        elif previous_cumulative is None:
            if record["model_output"] and usage_has_tokens(last):
                classification = "usage_update"
                contribution = last
            else:
                classification = "baseline_event"
            previous_cumulative = current
        elif all(current[key] == previous_cumulative[key] for key in USAGE_COMPONENTS):
            classification = "replayed_event"
        elif all(current[key] >= previous_cumulative[key] for key in USAGE_COMPONENTS):
            classification = "usage_update"
            contribution = {key: current[key] - previous_cumulative[key] for key in USAGE_COMPONENTS}
            previous_cumulative = current
        else:
            classification = "counter_reset"
            if record["model_output"] and usage_has_tokens(last):
                contribution = last
            previous_cumulative = current

        raw_usage = last or {key: 0 for key in USAGE_COMPONENTS}
        token_events.append(
            usage_event(thread_id, model, record["timestamp"], raw_usage, "reported", classification)
        )
        if (
            contribution
            and usage_has_tokens(contribution)
            and record["line_number"] not in covered_token_lines
        ):
            fallback_usage_events.append(
                usage_event(thread_id, model, record["timestamp"], contribution, "fallback", classification)
            )

    exact_usage_events: list[dict] = []
    for record in unique_exact_records:
        response_id = record["response_id"]
        exact_usage_events.append(
            usage_event(
                thread_id,
                model,
                record["timestamp"],
                record["usage"],
                "exact",
                "usage_update",
                response_id or None,
            )
        )

    return {
        "usage_events": sorted(fallback_usage_events + exact_usage_events, key=lambda event: event["timestamp"]),
        "token_events": token_events,
    }


def filter_telemetry_events(events: list[dict], filters: dict[str, str | int | bool | None]) -> list[dict]:
    start_day = filters.get("start_day")
    end_day = filters.get("end_day")
    return [
        event
        for event in events
        if (not start_day or event["day"] >= start_day) and (not end_day or event["day"] <= end_day)
    ]


def scan_token_telemetry(db_path: Path, start_ts: int | None, ignore_auto_review: bool) -> dict[str, list[dict]]:
    with connect(db_path) as conn:
        where_sql = "where rollout_path != ''"
        params: list[int] = []
        if start_ts is not None:
            where_sql += " and updated_at >= ?"
            params.append(start_ts)
        threads = conn.execute(
            f"""
            select id, rollout_path, coalesce(model, '(unknown)') model
            from threads
            {where_sql}
            """,
            params,
        ).fetchall()

    usage_events: list[dict] = []
    token_records: list[dict] = []
    seen_response_ids: set[str] = set()
    for thread in threads:
        if ignore_auto_review and thread["model"] == AUTO_REVIEW_MODEL:
            continue
        rollout_path = Path(thread["rollout_path"])
        if not rollout_path.exists():
            continue
        result = scan_rollout_telemetry(rollout_path, thread["id"], thread["model"])
        token_records.extend(result["token_events"])
        for event in result["usage_events"]:
            response_id = event.get("response_id")
            if response_id and response_id in seen_response_ids:
                continue
            if response_id:
                seen_response_ids.add(response_id)
            usage_events.append(event)
    return {"usage_events": usage_events, "token_events": token_records}


def token_events(db_path: Path, filters: dict[str, str | int | bool | None]) -> list[dict]:
    telemetry = scan_token_telemetry(db_path, filters.get("start_ts"), bool(filters.get("ignore_auto_review")))
    return filter_telemetry_events(telemetry["usage_events"], filters)


def chart_granularity(start_day: dt.date, end_day: dt.date) -> str:
    span_days = (end_day - start_day).days + 1
    if span_days <= 60:
        return "day"
    if span_days <= 183:
        return "week"
    return "month"


def chart_bucket_for_day(day: dt.date, granularity: str) -> tuple[dt.date, dt.date, str]:
    if granularity == "week":
        start = day - dt.timedelta(days=day.weekday())
        end = start + dt.timedelta(days=6)
        label = f"{start.strftime('%b')} {start.day}"
        return start, end, label
    if granularity == "month":
        start = day.replace(day=1)
        end = dt.date(day.year, day.month, days_in_month(day.year, day.month))
        label = start.strftime("%b %Y")
        return start, end, label
    return day, day, f"{day.strftime('%b')} {day.day}"


def chart_days_from_events(events: list[dict], filters: dict[str, str | int | bool | None]) -> dict:
    metric_keys = ("total_tokens", "total_with_cached_tokens")
    bucket_model_map: dict[str, dict[str, dict[str, int]]] = {}
    model_totals: dict[str, dict[str, int]] = {}
    start_day = parse_iso_day(str(filters["start_day"])) if filters.get("start_day") else None
    end_day = parse_iso_day(str(filters["end_day"])) if filters.get("end_day") else None

    event_days = [dt.date.fromisoformat(event["day"]) for event in events]
    if start_day is None and event_days:
        start_day = min(event_days)
    if end_day is None:
        if event_days:
            end_day = max(dt.date.today(), max(event_days))
        else:
            end_day = dt.date.today()
    if start_day is None:
        start_day = end_day

    granularity = chart_granularity(start_day, end_day)
    for event in events:
        event_day = dt.date.fromisoformat(event["day"])
        bucket_start, _, _ = chart_bucket_for_day(event_day, granularity)
        bucket_key = bucket_start.isoformat()
        model = event["model"]
        bucket_models = bucket_model_map.setdefault(bucket_key, {})
        bucket_totals = bucket_models.setdefault(model, {key: 0 for key in metric_keys})
        overall_totals = model_totals.setdefault(model, {key: 0 for key in metric_keys})
        for key in metric_keys:
            tokens = int(event[key])
            bucket_totals[key] += tokens
            overall_totals[key] += tokens

    days = []
    cursor, _, _ = chart_bucket_for_day(start_day, granularity)
    while cursor <= end_day:
        bucket_start, bucket_end, label = chart_bucket_for_day(cursor, granularity)
        day_key = bucket_start.isoformat()
        models = [
            {"model": model, **totals}
            for model, totals in sorted(
                bucket_model_map.get(day_key, {}).items(), key=lambda item: item[1]["total_tokens"], reverse=True
            )
            if totals["total_tokens"] or totals["total_with_cached_tokens"]
        ]
        days.append(
            {
                "day": day_key,
                "bucket_start": bucket_start.isoformat(),
                "bucket_end": bucket_end.isoformat(),
                "label": label,
                "total_tokens": sum(item["total_tokens"] for item in models),
                "total_with_cached_tokens": sum(item["total_with_cached_tokens"] for item in models),
                "models": models,
            }
        )
        if granularity == "month":
            cursor = add_months(bucket_start, 1)
        elif granularity == "week":
            cursor = bucket_start + dt.timedelta(days=7)
        else:
            cursor = bucket_start + dt.timedelta(days=1)

    models = [
        {"model": model, **totals}
        for model, totals in sorted(model_totals.items(), key=lambda item: item[1]["total_tokens"], reverse=True)
        if totals["total_tokens"] or totals["total_with_cached_tokens"]
    ]
    return {
        "range": filters["range"],
        "granularity": granularity,
        "range_start": start_day.isoformat() if start_day else None,
        "range_end": end_day.isoformat() if end_day else None,
        "days": days,
        "models": models,
    }


def diagnostics_from_events(usage_events: list[dict], token_records: list[dict]) -> dict:
    rows: dict[tuple[str, str], dict] = {}

    def row_for(event: dict) -> dict:
        key = (event["hour"], event["model"])
        return rows.setdefault(
            key,
            {
                "hour": event["hour"],
                "model": event["model"],
                "raw_token_events": 0,
                "deduplicated_usage_updates": 0,
                "replayed_events": 0,
                "baseline_events": 0,
                "counter_resets": 0,
                "unverifiable_events": 0,
                "exact_usage_events": 0,
                "fallback_usage_events": 0,
                "reported_tokens": 0,
                "deduplicated_tokens": 0,
            },
        )

    classification_keys = {
        "replayed_event": "replayed_events",
        "baseline_event": "baseline_events",
        "counter_reset": "counter_resets",
        "unverifiable_event": "unverifiable_events",
    }
    for event in token_records:
        row = row_for(event)
        row["raw_token_events"] += 1
        classification_key = classification_keys.get(event["classification"])
        if classification_key:
            row[classification_key] += 1
        row["reported_tokens"] += event["total_with_cached_tokens"]

    for event in usage_events:
        row = row_for(event)
        row["deduplicated_usage_updates"] += 1
        row[f'{event["source"]}_usage_events'] += 1
        row["deduplicated_tokens"] += event["total_with_cached_tokens"]

    result_rows = sorted(rows.values(), key=lambda row: (row["hour"], row["model"]), reverse=True)
    for row in result_rows:
        row["replay_rate"] = row["replayed_events"] / max(row["raw_token_events"], 1)
        row["estimated_local_overcount_tokens"] = max(row["reported_tokens"] - row["deduplicated_tokens"], 0)

    summary_keys = (
        "raw_token_events",
        "deduplicated_usage_updates",
        "replayed_events",
        "baseline_events",
        "counter_resets",
        "unverifiable_events",
        "exact_usage_events",
        "fallback_usage_events",
        "reported_tokens",
        "deduplicated_tokens",
    )
    summary = {key: sum(row[key] for row in result_rows) for key in summary_keys}
    summary["replay_rate"] = summary["replayed_events"] / max(summary["raw_token_events"], 1)
    summary["estimated_local_overcount_tokens"] = max(
        summary["reported_tokens"] - summary["deduplicated_tokens"], 0
    )
    return {"summary": summary, "rows": result_rows}


def load_usage(
    db_path: Path,
    range_name: str,
    start_day: str | None = None,
    end_day: str | None = None,
    ignore_auto_review: bool = False,
    chart_range: str | None = "30d",
    chart_start_day: str | None = None,
    chart_end_day: str | None = None,
    include_diagnostics: bool = False,
    provider: str = "codex",
    claude_projects_path: Path = DEFAULT_CLAUDE_PROJECTS,
    claude_db_path: Path = DEFAULT_CLAUDE_DB,
) -> dict:
    provider = normalize_provider(provider)
    if provider == "claude":
        ignore_auto_review = False
        include_diagnostics = False
    filters = resolve_range(range_name, start_day, end_day, ignore_auto_review)
    chart_filters = resolve_chart_range(chart_range, chart_start_day, chart_end_day, ignore_auto_review)
    start_timestamps = [filters["start_ts"], chart_filters["start_ts"]]
    scan_start_ts = None if any(value is None for value in start_timestamps) else min(int(value) for value in start_timestamps)
    indexing = None
    if provider == "claude":
        indexing = index_claude_usage(claude_projects_path, claude_db_path)
        telemetry = {"usage_events": load_claude_events(claude_db_path, scan_start_ts), "token_events": []}
    else:
        telemetry = scan_token_telemetry(db_path, scan_start_ts, ignore_auto_review)
    events = filter_telemetry_events(telemetry["usage_events"], filters)
    chart_events = filter_telemetry_events(telemetry["usage_events"], chart_filters)
    diagnostic_token_records = filter_telemetry_events(telemetry["token_events"], filters)
    pricing = load_pricing()
    missing_price_models = set()

    daily_map: dict[str, dict] = {}
    model_map: dict[str, dict] = {}
    thread_ids = set()
    for event in events:
        event_cost, missing_model = token_cost_usd(event, pricing)
        if missing_model:
            missing_price_models.add(missing_model)
        event["cost_usd"] = event_cost
        thread_ids.add(event["thread_id"])
        day = event["day"]
        model = event["model"]
        daily = daily_map.setdefault(
            day,
            {
                "day": day,
                "sessions": set(),
                "input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cached_input_tokens": 0,
                "raw_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
                "total_with_cached_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        daily["sessions"].add(event["thread_id"])
        model_row = model_map.setdefault(
            model,
            {
                "model": model,
                "sessions": set(),
                "input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cached_input_tokens": 0,
                "raw_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
                "total_with_cached_tokens": 0,
                "cost_usd": 0.0,
                "daily_map": {},
            },
        )
        model_row["sessions"].add(event["thread_id"])
        model_daily = model_row["daily_map"].setdefault(
            day,
            {
                "day": day,
                "sessions": set(),
                "input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "cached_input_tokens": 0,
                "raw_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
                "total_with_cached_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        model_daily["sessions"].add(event["thread_id"])
        for key in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "cached_input_tokens",
            "raw_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "total_tokens",
            "total_with_cached_tokens",
            "cost_usd",
        ):
            daily[key] += event[key]
            model_row[key] += event[key]
            model_daily[key] += event[key]

    day_rows = sorted(daily_map.values(), key=lambda row: row["day"])
    for row in day_rows:
        row["sessions"] = len(row["sessions"])

    model_rows = sorted(model_map.values(), key=lambda row: (row["total_tokens"], len(row["sessions"])), reverse=True)
    for row in model_rows:
        row["sessions"] = len(row["sessions"])
        daily_rows = sorted(row.pop("daily_map").values(), key=lambda item: item["day"], reverse=True)
        for item in daily_rows:
            item["sessions"] = len(item["sessions"])
        row["active_days"] = len(daily_rows)
        row["daily"] = daily_rows

    days = {row["day"] for row in day_rows}
    favorite = model_rows[0]["model"] if model_rows else "-"
    peak = max(day_rows, key=lambda row: row["total_tokens"], default=None)
    total_input = sum(row["input_tokens"] for row in day_rows)
    total_cache_creation = sum(row["cache_creation_input_tokens"] for row in day_rows)
    total_cache_read = sum(row["cache_read_input_tokens"] for row in day_rows)
    total_cached = sum(row["cached_input_tokens"] for row in day_rows)
    total_output = sum(row["output_tokens"] for row in day_rows)
    total_reasoning = sum(row["reasoning_output_tokens"] for row in day_rows)
    total_tokens = sum(row["total_tokens"] for row in day_rows)
    total_with_cached = sum(row["total_with_cached_tokens"] for row in day_rows)
    total_cost = sum(row["cost_usd"] for row in day_rows)

    provider_label = "Claude" if provider == "claude" else "Codex"
    result = {
        "provider": provider,
        "provider_label": provider_label,
        "data_source": "Claude JSONL → SQLite" if provider == "claude" else "SQLite + JSONL",
        "supports_diagnostics": provider == "codex",
        "range": filters["range"],
        "range_start": filters["start_day"],
        "range_end": filters["end_day"],
        "ignore_auto_review": bool(filters["ignore_auto_review"]),
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "totals": {
            "sessions": len(thread_ids),
            "active_days": len(days),
            "input_tokens": total_input,
            "cache_creation_input_tokens": total_cache_creation,
            "cache_read_input_tokens": total_cache_read,
            "cached_input_tokens": total_cached,
            "output_tokens": total_output,
            "reasoning_output_tokens": total_reasoning,
            "total_tokens": total_tokens,
            "total_with_cached_tokens": total_with_cached,
            "cost_usd": total_cost,
        },
        "daily": day_rows,
        "models": model_rows,
        "chart": chart_days_from_events(chart_events, chart_filters),
        "pricing": {
            "source": pricing["source"],
            "url": pricing["url"],
            "loaded_at": pricing["loaded_at"],
            "error": pricing["error"],
            "missing_models": sorted(missing_price_models),
        },
        "favorite_model": favorite,
        "current_streak": current_streak(days),
        "longest_streak": longest_streak(days),
        "peak_day": peak["day"] if peak else "-",
        "peak_day_tokens": peak["total_tokens"] if peak else 0,
    }
    if indexing is not None:
        result["indexing"] = indexing
    if include_diagnostics:
        result["diagnostics"] = diagnostics_from_events(events, diagnostic_token_records)
    return result


def heatmap_days(
    daily: list[dict],
    range_name: str,
    start_day: str | None = None,
    end_day: str | None = None,
) -> list[dict]:
    by_day = {row["day"]: row for row in daily}
    selected_start = parse_iso_day(start_day)
    selected_end = parse_iso_day(end_day)
    if range_name == "all":
        if daily:
            first = dt.date.fromisoformat(daily[0]["day"])
            last = max(dt.date.today(), dt.date.fromisoformat(daily[-1]["day"]))
        else:
            first = dt.date.today()
            last = dt.date.today()
    else:
        first = selected_start or (dt.date.fromisoformat(daily[0]["day"]) if daily else dt.date.today())
        last = selected_end or first

    # Align to Monday for a stable contribution-grid shape.
    first -= dt.timedelta(days=first.weekday())
    max_tokens = max((row["total_tokens"] for row in daily), default=0)
    cells = []
    cursor = first
    while cursor <= last:
        key = cursor.isoformat()
        row = by_day.get(key, {"sessions": 0, "total_tokens": 0})
        tokens = row["total_tokens"]
        if tokens == 0 or max_tokens == 0:
            level = 0
        elif tokens < max_tokens * 0.2:
            level = 1
        elif tokens < max_tokens * 0.45:
            level = 2
        elif tokens < max_tokens * 0.7:
            level = 3
        else:
            level = 4
        cells.append({"day": key, "sessions": row["sessions"], "tokens": tokens, "level": level})
        cursor += dt.timedelta(days=1)
    return cells


def render_dashboard(data: dict) -> str:
    provider = data.get("provider", "codex")
    provider_label = data.get("provider_label", "Codex")
    totals = data["totals"]
    daily_desc = list(reversed(data["daily"]))
    heat_cells = heatmap_days(data["daily"], data["range"], data.get("range_start"), data.get("range_end"))
    heat_columns = max(1, (len(heat_cells) + 6) // 7)

    if data["range"] == "custom" and data.get("range_start") and data.get("range_end"):
        range_summary = f'{data["range_start"]} to {data["range_end"]}'
    elif data["range"] == "1d" and data.get("range_start"):
        range_summary = data["range_start"]
    elif data["range"] == "7d":
        range_summary = "Last 7 days"
    elif data["range"] == "30d":
        range_summary = "Last 30 days"
    else:
        range_summary = "All time"

    def range_link(label: str, value: str) -> str:
        active = " active" if data["range"] == value else ""
        return f'<a class="seg{active}" href="/?provider={provider}&range={value}">{label}</a>'

    day_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(row["day"])}</td>
          <td>All</td>
          <td>{html.escape(str(provider_label))}</td>
          <td class="num">{fmt_int(row["input_tokens"])}</td>
          <td class="num">{fmt_int(row["output_tokens"])}</td>
          <td class="num">{fmt_int(row["total_tokens"])}</td>
          <td class="num">{fmt_int(row["cached_input_tokens"])}</td>
          <td class="num">{fmt_int(row["total_with_cached_tokens"])}</td>
          <td class="num">{fmt_usd(row["cost_usd"])}</td>
          <td class="num">{fmt_int(row["sessions"])}</td>
        </tr>
        """
        for row in daily_desc
    ) or '<tr><td colspan="10" class="empty">No usage in this range.</td></tr>'

    model_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(row["model"])}</td>
          <td class="num">{fmt_int(row["sessions"])}</td>
          <td class="num">{fmt_int(row["input_tokens"])}</td>
          <td class="num">{fmt_int(row["output_tokens"])}</td>
          <td class="num">{fmt_int(row["total_tokens"])}</td>
          <td class="num">{fmt_int(row["cached_input_tokens"])}</td>
          <td class="num">{fmt_int(row["total_with_cached_tokens"])}</td>
          <td class="num">{fmt_usd(row["cost_usd"])}</td>
          <td class="num">{(row["total_tokens"] / max(totals["total_tokens"], 1) * 100):.1f}%</td>
        </tr>
        """
        for row in data["models"]
    ) or '<tr><td colspan="9" class="empty">No models in this range.</td></tr>'

    heatmap = "\n".join(
        f"""
        <div class="heat-cell level-{cell["level"]}" title="{html.escape(cell["day"])}: {fmt_int(cell["tokens"])} tokens, {fmt_int(cell["sessions"])} sessions"></div>
        """
        for cell in heat_cells
    )

    peak_value = data["peak_day"]
    if data["peak_day_tokens"]:
        peak_value = f'{peak_value}<span class="metric-note">{fmt_short(data["peak_day_tokens"])}</span>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(str(provider_label))} Usage Dashboard</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #151515;
      --panel: #232323;
      --panel-2: #303030;
      --line: #444;
      --text: #f2f2f2;
      --muted: #a8a8a8;
      --accent: #84aef2;
      --accent-2: #d7df3f;
      --green-0: #303030;
      --green-1: #294761;
      --green-2: #2f67a2;
      --green-3: #3e87d6;
      --green-4: #7fb0f2;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      font-size: 16px;
      line-height: 1.45;
    }}
    main {{
      width: min(1534px, calc(100vw - 32px));
      margin: 28px auto 56px;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: flex-start;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 30px;
      font-weight: 760;
      letter-spacing: 0;
    }}
    .subtle {{ color: var(--muted); }}
    .segments {{
      display: flex;
      gap: 8px;
      background: var(--panel);
      border: 1px solid var(--line);
      padding: 6px;
      border-radius: 8px;
      white-space: nowrap;
    }}
    .seg {{
      color: var(--muted);
      text-decoration: none;
      padding: 7px 13px;
      border-radius: 6px;
      min-height: 38px;
      display: inline-flex;
      align-items: center;
    }}
    .seg.active {{
      background: var(--panel-2);
      color: var(--text);
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      min-height: 92px;
    }}
    .label {{
      color: var(--muted);
      font-size: 15px;
      margin-bottom: 6px;
    }}
    .value {{
      font-size: 27px;
      font-weight: 760;
      overflow-wrap: anywhere;
    }}
    .metric-note {{
      display: block;
      color: var(--muted);
      font-size: 14px;
      font-weight: 500;
      margin-top: 4px;
    }}
    section {{
      margin-top: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .heat-wrap {{
      overflow-x: auto;
      padding-bottom: 4px;
    }}
    .heatmap {{
      display: grid;
      grid-auto-flow: column;
      grid-template-rows: repeat(7, 16px);
      grid-template-columns: repeat({heat_columns}, 16px);
      gap: 5px;
      width: max-content;
    }}
    .heat-cell {{
      width: 16px;
      height: 16px;
      border-radius: 4px;
      background: var(--green-0);
      border: 1px solid rgba(255,255,255,.04);
    }}
    .level-1 {{ background: var(--green-1); }}
    .level-2 {{ background: var(--green-2); }}
    .level-3 {{ background: var(--green-3); }}
    .level-4 {{ background: var(--green-4); }}
    .tables {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(360px, .9fr);
      gap: 18px;
      align-items: start;
    }}
    .table-scroll {{ overflow-x: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 936px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-size: 14px;
      font-weight: 650;
    }}
    td.num, th.num {{
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    td.empty {{
      color: var(--muted);
      text-align: center;
      padding: 26px 12px;
    }}
    tfoot td {{
      color: var(--accent-2);
      font-weight: 760;
      border-bottom: 0;
    }}
    details {{
      margin-top: 18px;
      color: var(--muted);
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #101010;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      max-height: 420px;
      overflow: auto;
    }}
    @media (max-width: 880px) {{
      header {{ flex-direction: column; }}
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .tables {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 520px) {{
      main {{ width: min(100vw - 20px, 1534px); margin-top: 18px; }}
      .cards {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 25px; }}
      .value {{ font-size: 23px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{html.escape(str(provider_label))} Usage</h1>
        <div class="subtle">Generated {html.escape(data["generated_at"])} from {html.escape(str(data.get("data_source", "local logs")))} · <a href="/data.json?provider={provider}&range={html.escape(data["range"])}">aggregate JSON</a></div>
        <div class="subtle">Showing {html.escape(range_summary)}</div>
      </div>
      <nav class="segments" aria-label="Range">
        {range_link("All", "all")}
        {range_link("30d", "30d")}
        {range_link("7d", "7d")}
        {range_link("1d", "1d")}
        {range_link("Custom", "custom")}
      </nav>
    </header>

    <div class="cards">
      <div class="card"><div class="label">Sessions</div><div class="value">{fmt_int(totals["sessions"])}</div></div>
      <div class="card"><div class="label">Input tokens</div><div class="value">{fmt_short(totals["input_tokens"])}</div></div>
      <div class="card"><div class="label">Output tokens</div><div class="value">{fmt_short(totals["output_tokens"])}</div></div>
      <div class="card"><div class="label">Total w/o cached</div><div class="value">{fmt_short(totals["total_tokens"])}</div></div>
      <div class="card"><div class="label">Cached input</div><div class="value">{fmt_short(totals["cached_input_tokens"])}</div></div>
      <div class="card"><div class="label">Total tokens</div><div class="value">{fmt_short(totals["total_with_cached_tokens"])}</div></div>
      <div class="card"><div class="label">Active days</div><div class="value">{fmt_int(totals["active_days"])}</div></div>
      <div class="card"><div class="label">API estimate</div><div class="value">{fmt_usd(totals["cost_usd"])}<span class="metric-note">{html.escape(data["pricing"]["source"])}</span></div></div>
      <div class="card"><div class="label">Favorite model</div><div class="value">{html.escape(data["favorite_model"])}</div></div>
      <div class="card"><div class="label">Current streak</div><div class="value">{fmt_int(data["current_streak"])}d</div></div>
      <div class="card"><div class="label">Longest streak</div><div class="value">{fmt_int(data["longest_streak"])}d</div></div>
      <div class="card"><div class="label">Peak day</div><div class="value">{peak_value}</div></div>
      <div class="card"><div class="label">Data source</div><div class="value">SQLite</div></div>
    </div>

    <section>
      <h2>Daily Heatmap</h2>
      <div class="heat-wrap"><div class="heatmap">{heatmap}</div></div>
    </section>

    <div class="tables">
      <section>
        <h2>Daily Usage</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Date</th><th>Scope</th><th>App</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total w/o cached</th><th class="num">Cached</th><th class="num">Total</th><th class="num">Cost</th><th class="num">Sessions</th></tr></thead>
            <tbody>{day_rows}</tbody>
            <tfoot><tr><td>Total</td><td></td><td></td><td class="num">{fmt_int(totals["input_tokens"])}</td><td class="num">{fmt_int(totals["output_tokens"])}</td><td class="num">{fmt_int(totals["total_tokens"])}</td><td class="num">{fmt_int(totals["cached_input_tokens"])}</td><td class="num">{fmt_int(totals["total_with_cached_tokens"])}</td><td class="num">{fmt_usd(totals["cost_usd"])}</td><td class="num">{fmt_int(totals["sessions"])}</td></tr></tfoot>
          </table>
        </div>
      </section>

      <section>
        <h2>Models</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Model</th><th class="num">Sessions</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total w/o cached</th><th class="num">Cached</th><th class="num">Total</th><th class="num">Cost</th><th class="num">Share</th></tr></thead>
            <tbody>{model_rows}</tbody>
          </table>
        </div>
      </section>
    </div>

  </main>
</body>
</html>"""


def render_error_page(message: str, db_path: Path) -> str:
    safe_message = html.escape(message)
    safe_path = html.escape(str(db_path))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Usage Dashboard</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0;
      background: #151515;
      color: #f2f2f2;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      line-height: 1.45;
    }}
    main {{
      width: min(760px, calc(100vw - 32px));
      margin: 48px auto;
      background: #232323;
      border: 1px solid #444;
      border-radius: 8px;
      padding: 20px;
    }}
    h1 {{ margin: 0 0 12px; font-size: 24px; }}
    code {{
      display: block;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: #101010;
      border: 1px solid #444;
      border-radius: 8px;
      padding: 12px;
      margin-top: 12px;
    }}
    .muted {{ color: #a8a8a8; }}
  </style>
</head>
<body>
  <main>
    <h1>Codex Usage</h1>
    <p>Could not read the Codex state database.</p>
    <code>{safe_message}</code>
    <p class="muted">Data source: {safe_path}</p>
  </main>
</body>
</html>"""


class DashboardHandler(BaseHTTPRequestHandler):
    db_path: Path = DEFAULT_DB
    claude_projects_path: Path = DEFAULT_CLAUDE_PROJECTS
    claude_db_path: Path = DEFAULT_CLAUDE_DB

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.serve_dashboard(parsed.query)
            return
        if parsed.path in {"/data.json", "/api/usage"}:
            self.serve_json(parsed.query)
            return
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        self.send_error(404)

    def filters_from_query(self, query_string: str) -> dict[str, str | int | bool | None]:
        query = parse_qs(query_string)
        provider = normalize_provider(query.get("provider", ["codex"])[0])
        filters = resolve_range(
            query.get("range", ["all"])[0],
            query.get("start", [None])[0],
            query.get("end", [None])[0],
            parse_bool_flag(query.get("ignore_auto_review", [None])[0], default=False) if provider == "codex" else False,
        )
        filters["provider"] = provider
        chart_filters = resolve_chart_range(
            query.get("chart_range", ["30d"])[0],
            query.get("chart_start", [None])[0],
            query.get("chart_end", [None])[0],
            bool(filters["ignore_auto_review"]),
        )
        filters["chart_range"] = chart_filters["range"]
        filters["chart_start_day"] = chart_filters["start_day"]
        filters["chart_end_day"] = chart_filters["end_day"]
        filters["include_diagnostics"] = provider == "codex" and parse_bool_flag(
            query.get("include_diagnostics", [None])[0], default=False
        )
        return filters

    def send_body(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def serve_dashboard(self, query_string: str) -> None:
        filters = self.filters_from_query(query_string)
        try:
            data = load_usage(
                self.db_path,
                str(filters["range"]),
                filters["start_day"],
                filters["end_day"],
                bool(filters["ignore_auto_review"]),
                str(filters["chart_range"]),
                filters["chart_start_day"],
                filters["chart_end_day"],
                bool(filters["include_diagnostics"]),
                provider=str(filters["provider"]),
                claude_projects_path=self.claude_projects_path,
                claude_db_path=self.claude_db_path,
            )
            body = render_dashboard(data).encode("utf-8")
            self.send_body(200, "text/html; charset=utf-8", body)
        except Exception as exc:  # noqa: BLE001
            source_path = self.claude_projects_path if filters["provider"] == "claude" else self.db_path
            body = render_error_page(str(exc), source_path).encode("utf-8")
            self.send_body(503, "text/html; charset=utf-8", body)

    def serve_json(self, query_string: str) -> None:
        filters = self.filters_from_query(query_string)
        try:
            payload = load_usage(
                self.db_path,
                str(filters["range"]),
                filters["start_day"],
                filters["end_day"],
                bool(filters["ignore_auto_review"]),
                str(filters["chart_range"]),
                filters["chart_start_day"],
                filters["chart_end_day"],
                bool(filters["include_diagnostics"]),
                provider=str(filters["provider"]),
                claude_projects_path=self.claude_projects_path,
                claude_db_path=self.claude_db_path,
            )
            status = 200
        except Exception as exc:  # noqa: BLE001
            provider_label = "Claude" if filters["provider"] == "claude" else "Codex"
            payload = {
                "error": f"Could not read {provider_label} usage data.",
                "provider": filters["provider"],
                "provider_label": provider_label,
                "range": filters["range"],
                "range_start": filters["start_day"],
                "range_end": filters["end_day"],
                "ignore_auto_review": bool(filters["ignore_auto_review"]),
                "chart_range": filters["chart_range"],
                "chart_start": filters["chart_start_day"],
                "chart_end": filters["chart_end_day"],
                "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            status = 503
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_body(status, "application/json; charset=utf-8", body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def run_check(db_path: Path) -> None:
    sample_cost, missing_model = token_cost_usd(
        {
            "model": "gpt-5.5",
            "input_tokens": 2_429_884,
            "cached_input_tokens": 40_193_280,
            "output_tokens": 195_249,
        },
        {"models": FALLBACK_PRICING, "fallback": FALLBACK_PRICING},
    )
    if missing_model or round(sample_cost, 5) != 38.10353:
        raise RuntimeError("Cost calculation check failed")

    checks = [
        ("all", None, None, False, "30d", None, None, "day"),
        ("30d", None, None, False, "90d", None, None, "week"),
        ("30d", None, None, False, "6m", None, None, "week"),
        ("30d", None, None, False, "1y", None, None, "month"),
        ("7d", None, None, False, "all", None, None, None),
        ("1d", None, None, False, "custom", "2026-01-01", "2026-01-03", "day"),
        ("1d", None, None, False, "custom", "2026-01-01", "2026-03-01", "day"),
        ("1d", None, None, False, "custom", "2026-01-01", "2026-03-02", "week"),
        ("1d", None, None, False, "custom", "2026-01-01", "2026-05-01", "week"),
        ("1d", None, None, False, "custom", "2026-01-01", "2026-12-31", "month"),
        ("custom", "2026-01-01", "2026-01-03", False, "30d", None, None, "day"),
        ("bad-range", None, None, False, "bad-range", None, None, "day"),
        ("all", None, None, True, "30d", None, None, "day"),
    ]
    for range_name, start_day, end_day, ignore_auto_review, chart_range, chart_start, chart_end, expected_granularity in checks:
        data = load_usage(db_path, range_name, start_day, end_day, ignore_auto_review, chart_range, chart_start, chart_end)
        html_body = render_dashboard(data)
        json.dumps(data, ensure_ascii=False)
        chart = data["chart"]
        if chart["range"] not in {"all", "1y", "6m", "90d", "30d", "custom"}:
            raise RuntimeError(f"Chart range failed for range={range_name}")
        if chart["granularity"] not in {"day", "week", "month"}:
            raise RuntimeError(f"Chart granularity failed for range={range_name}")
        if expected_granularity and chart["granularity"] != expected_granularity:
            raise RuntimeError(
                f"Expected {expected_granularity} chart granularity for chart_range={chart_range}, got {chart['granularity']}"
            )
        for day_row in chart["days"]:
            model_total = sum(item["total_tokens"] for item in day_row["models"])
            if day_row["total_tokens"] != model_total:
                raise RuntimeError(f"Chart day model sum failed for range={range_name}")
        chart_model_totals = {}
        for day_row in chart["days"]:
            for item in day_row["models"]:
                chart_model_totals[item["model"]] = chart_model_totals.get(item["model"], 0) + item["total_tokens"]
        for model_row in chart["models"]:
            if model_row["total_tokens"] != chart_model_totals.get(model_row["model"], 0):
                raise RuntimeError(f"Chart model sum failed for range={range_name}")
        totals = data["totals"]
        if totals["total_tokens"] != totals["input_tokens"] + totals["output_tokens"]:
            raise RuntimeError(f"Total without cached invariant failed for range={range_name}")
        if totals["total_with_cached_tokens"] != totals["total_tokens"] + totals["cached_input_tokens"]:
            raise RuntimeError(f"Total with cached invariant failed for range={range_name}")
        for row in data["daily"]:
            if row["total_tokens"] != row["input_tokens"] + row["output_tokens"]:
                raise RuntimeError(f"Daily total without cached invariant failed for range={range_name}")
            if row["total_with_cached_tokens"] != row["total_tokens"] + row["cached_input_tokens"]:
                raise RuntimeError(f"Daily total with cached invariant failed for range={range_name}")
        for row in data["models"]:
            if row["total_tokens"] != row["input_tokens"] + row["output_tokens"]:
                raise RuntimeError(f"Model total without cached invariant failed for range={range_name}")
            if row["total_with_cached_tokens"] != row["total_tokens"] + row["cached_input_tokens"]:
                raise RuntimeError(f"Model total with cached invariant failed for range={range_name}")
        if "<!doctype html>" not in html_body:
            raise RuntimeError(f"Dashboard render failed for range={range_name}")
    print(f"Smoke check passed for {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a local Codex and Claude usage dashboard.")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("CODEX_USAGE_DB", DEFAULT_DB)))
    parser.add_argument(
        "--claude-projects",
        type=Path,
        default=Path(os.environ.get("CLAUDE_PROJECTS_DIR", DEFAULT_CLAUDE_PROJECTS)),
    )
    parser.add_argument(
        "--claude-db",
        type=Path,
        default=Path(os.environ.get("CLAUDE_USAGE_DB", DEFAULT_CLAUDE_DB)),
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Render all ranges once and exit.")
    args = parser.parse_args()

    DashboardHandler.db_path = args.db.expanduser()
    DashboardHandler.claude_projects_path = args.claude_projects.expanduser()
    DashboardHandler.claude_db_path = args.claude_db.expanduser()
    if args.check:
        run_check(DashboardHandler.db_path)
        return

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Codex + Claude usage dashboard: http://{args.host}:{args.port}")
    print(f"Codex source: {DashboardHandler.db_path}")
    print(f"Claude source: {DashboardHandler.claude_projects_path}")
    print(f"Claude index: {DashboardHandler.claude_db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
