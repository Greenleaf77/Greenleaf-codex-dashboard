#!/usr/bin/env python3
"""Local Codex usage dashboard backed by ~/.codex/state_5.sqlite."""

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


DEFAULT_DB = Path.home() / ".codex" / "state_5.sqlite"
RANGES = {"all", "30d", "7d"}


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


def iso_from_unix(value: int | None) -> str:
    if value is None:
        return "-"
    return dt.datetime.fromtimestamp(value).date().isoformat()


def day_from_iso_timestamp(value: str) -> str:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().date().isoformat()


def normalize_range(range_name: str | None) -> str:
    return range_name if range_name in RANGES else "all"


def range_start(range_name: str) -> tuple[str | None, int | None]:
    range_name = normalize_range(range_name)
    if range_name == "7d":
        start = (dt.datetime.now() - dt.timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start.date().isoformat(), int(start.timestamp())
    if range_name == "30d":
        start = (dt.datetime.now() - dt.timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)
        return start.date().isoformat(), int(start.timestamp())
    return None, None


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


def token_events(db_path: Path, range_name: str) -> list[dict]:
    start_day, start_ts = range_start(range_name)
    events: list[dict] = []
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

    for thread in threads:
        rollout_path = Path(thread["rollout_path"])
        if not rollout_path.exists():
            continue
        with rollout_path.open(encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if '"token_count"' not in line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = item.get("payload") or {}
                if payload.get("type") != "token_count":
                    continue
                timestamp = item.get("timestamp")
                if not timestamp:
                    continue
                day = day_from_iso_timestamp(timestamp)
                if start_day and day < start_day:
                    continue

                usage = ((payload.get("info") or {}).get("last_token_usage") or {})
                input_tokens = int(usage.get("input_tokens") or 0)
                cached_input_tokens = int(usage.get("cached_input_tokens") or 0)
                output_tokens = int(usage.get("output_tokens") or 0)
                reasoning_output_tokens = int(usage.get("reasoning_output_tokens") or 0)
                billable_input_tokens = max(input_tokens - cached_input_tokens, 0)
                # Keep every token_count usage event. This matches ccusage-style
                # accounting for Codex logs; deduping repeated cumulative totals
                # undercounts days such as 2026-05-22 in the local data.
                events.append(
                    {
                        "thread_id": thread["id"],
                        "day": day,
                        "model": thread["model"],
                        "input_tokens": billable_input_tokens,
                        "cached_input_tokens": cached_input_tokens,
                        "raw_input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "reasoning_output_tokens": reasoning_output_tokens,
                        "total_tokens": billable_input_tokens + output_tokens,
                    }
                )
    return events


def load_usage(db_path: Path, range_name: str) -> dict:
    range_name = normalize_range(range_name)
    events = token_events(db_path, range_name)

    daily_map: dict[str, dict] = {}
    model_map: dict[str, dict] = {}
    thread_ids = set()
    for event in events:
        thread_ids.add(event["thread_id"])
        day = event["day"]
        model = event["model"]
        daily = daily_map.setdefault(
            day,
            {
                "day": day,
                "sessions": set(),
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "raw_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
            },
        )
        daily["sessions"].add(event["thread_id"])
        model_row = model_map.setdefault(
            model,
            {
                "model": model,
                "sessions": set(),
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "raw_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
                "total_tokens": 0,
            },
        )
        model_row["sessions"].add(event["thread_id"])
        for key in (
            "input_tokens",
            "cached_input_tokens",
            "raw_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
            "total_tokens",
        ):
            daily[key] += event[key]
            model_row[key] += event[key]

    day_rows = sorted(daily_map.values(), key=lambda row: row["day"])
    for row in day_rows:
        row["sessions"] = len(row["sessions"])

    model_rows = sorted(model_map.values(), key=lambda row: (row["total_tokens"], row["sessions"]), reverse=True)
    for row in model_rows:
        row["sessions"] = len(row["sessions"])

    days = {row["day"] for row in day_rows}
    favorite = model_rows[0]["model"] if model_rows else "-"
    peak = max(day_rows, key=lambda row: row["total_tokens"], default=None)
    total_input = sum(row["input_tokens"] for row in day_rows)
    total_cached = sum(row["cached_input_tokens"] for row in day_rows)
    total_output = sum(row["output_tokens"] for row in day_rows)
    total_reasoning = sum(row["reasoning_output_tokens"] for row in day_rows)
    total_tokens = sum(row["total_tokens"] for row in day_rows)

    return {
        "range": range_name,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "totals": {
            "sessions": len(thread_ids),
            "active_days": len(days),
            "input_tokens": total_input,
            "cached_input_tokens": total_cached,
            "output_tokens": total_output,
            "reasoning_output_tokens": total_reasoning,
            "total_tokens": total_tokens,
        },
        "daily": day_rows,
        "models": model_rows,
        "favorite_model": favorite,
        "current_streak": current_streak(days),
        "longest_streak": longest_streak(days),
        "peak_day": peak["day"] if peak else "-",
        "peak_day_tokens": peak["total_tokens"] if peak else 0,
    }


def heatmap_days(daily: list[dict], range_name: str) -> list[dict]:
    by_day = {row["day"]: row for row in daily}
    if daily:
        first = dt.date.fromisoformat(daily[0]["day"])
        last = max(dt.date.today(), dt.date.fromisoformat(daily[-1]["day"]))
    else:
        first = dt.date.today()
        last = dt.date.today()

    if range_name == "7d":
        first = dt.date.today() - dt.timedelta(days=6)
    elif range_name == "30d":
        first = dt.date.today() - dt.timedelta(days=29)

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
    totals = data["totals"]
    daily_desc = list(reversed(data["daily"]))
    heat_cells = heatmap_days(data["daily"], data["range"])
    heat_columns = max(1, (len(heat_cells) + 6) // 7)

    def range_link(label: str, value: str) -> str:
        active = " active" if data["range"] == value else ""
        return f'<a class="seg{active}" href="/?range={value}">{label}</a>'

    day_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(row["day"])}</td>
          <td>All</td>
          <td>Codex</td>
          <td class="num">{fmt_int(row["input_tokens"])}</td>
          <td class="num">{fmt_int(row["output_tokens"])}</td>
          <td class="num">{fmt_int(row["total_tokens"])}</td>
          <td class="num">{fmt_int(row["sessions"])}</td>
        </tr>
        """
        for row in daily_desc
    ) or '<tr><td colspan="7" class="empty">No usage in this range.</td></tr>'

    model_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(row["model"])}</td>
          <td class="num">{fmt_int(row["sessions"])}</td>
          <td class="num">{fmt_int(row["input_tokens"])}</td>
          <td class="num">{fmt_int(row["output_tokens"])}</td>
          <td class="num">{fmt_int(row["total_tokens"])}</td>
          <td class="num">{(row["total_tokens"] / max(totals["total_tokens"], 1) * 100):.1f}%</td>
        </tr>
        """
        for row in data["models"]
    ) or '<tr><td colspan="6" class="empty">No models in this range.</td></tr>'

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
  <title>Codex Usage Dashboard</title>
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
      width: min(1180px, calc(100vw - 32px));
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
      min-width: 720px;
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
      main {{ width: min(100vw - 20px, 1180px); margin-top: 18px; }}
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
        <h1>Codex Usage</h1>
        <div class="subtle">Generated {html.escape(data["generated_at"])} from ~/.codex/state_5.sqlite · <a href="/data.json?range={html.escape(data["range"])}">aggregate JSON</a></div>
      </div>
      <nav class="segments" aria-label="Range">
        {range_link("All", "all")}
        {range_link("30d", "30d")}
        {range_link("7d", "7d")}
      </nav>
    </header>

    <div class="cards">
      <div class="card"><div class="label">Sessions</div><div class="value">{fmt_int(totals["sessions"])}</div></div>
      <div class="card"><div class="label">Total tokens</div><div class="value">{fmt_short(totals["total_tokens"])}</div></div>
      <div class="card"><div class="label">Input tokens</div><div class="value">{fmt_short(totals["input_tokens"])}</div></div>
      <div class="card"><div class="label">Output tokens</div><div class="value">{fmt_short(totals["output_tokens"])}</div></div>
      <div class="card"><div class="label">Active days</div><div class="value">{fmt_int(totals["active_days"])}</div></div>
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
            <thead><tr><th>Date</th><th>Scope</th><th>App</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total</th><th class="num">Sessions</th></tr></thead>
            <tbody>{day_rows}</tbody>
            <tfoot><tr><td>Total</td><td></td><td></td><td class="num">{fmt_int(totals["input_tokens"])}</td><td class="num">{fmt_int(totals["output_tokens"])}</td><td class="num">{fmt_int(totals["total_tokens"])}</td><td class="num">{fmt_int(totals["sessions"])}</td></tr></tfoot>
          </table>
        </div>
      </section>

      <section>
        <h2>Models</h2>
        <div class="table-scroll">
          <table>
            <thead><tr><th>Model</th><th class="num">Sessions</th><th class="num">Input</th><th class="num">Output</th><th class="num">Total</th><th class="num">Share</th></tr></thead>
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

    def range_from_query(self, query_string: str) -> str:
        query = parse_qs(query_string)
        return normalize_range(query.get("range", ["all"])[0])

    def send_body(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def serve_dashboard(self, query_string: str) -> None:
        range_name = self.range_from_query(query_string)
        try:
            data = load_usage(self.db_path, range_name)
            body = render_dashboard(data).encode("utf-8")
            self.send_body(200, "text/html; charset=utf-8", body)
        except Exception as exc:  # noqa: BLE001
            body = render_error_page(str(exc), self.db_path).encode("utf-8")
            self.send_body(503, "text/html; charset=utf-8", body)

    def serve_json(self, query_string: str) -> None:
        range_name = self.range_from_query(query_string)
        try:
            payload = load_usage(self.db_path, range_name)
            status = 200
        except Exception as exc:  # noqa: BLE001
            payload = {
                "error": "Could not read Codex usage data.",
                "range": range_name,
                "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            status = 503
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_body(status, "application/json; charset=utf-8", body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def run_check(db_path: Path) -> None:
    for range_name in ("all", "30d", "7d", "bad-range"):
        data = load_usage(db_path, range_name)
        html_body = render_dashboard(data)
        json.dumps(data, ensure_ascii=False)
        if "<!doctype html>" not in html_body:
            raise RuntimeError(f"Dashboard render failed for range={range_name}")
    print(f"Smoke check passed for {db_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a local Codex usage dashboard.")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("CODEX_USAGE_DB", DEFAULT_DB)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Render all ranges once and exit.")
    args = parser.parse_args()

    DashboardHandler.db_path = args.db.expanduser()
    if args.check:
        run_check(DashboardHandler.db_path)
        return

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Codex usage dashboard: http://{args.host}:{args.port}")
    print(f"Data source: {DashboardHandler.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
