#!/usr/bin/env python3
"""Flatten the MeterMesh API payloads into shell assignments for smoke.sh.

Reads the /api/usage and /api/settings responses and prints KEY=VALUE lines for
`eval`. Missing values print as '-' so a dropped mount surfaces as a readable
assertion diff rather than a Python traceback.

Usage: probe.py <usage.json> <settings.json>
"""
from __future__ import annotations

import json
import sys

# Recorded in the state_5.sqlite fixture. Wins only when the host-absolute
# rollout_path resolves inside the container.
STATE_MODEL_KEY = "codex:smoke-codex-state-model"
# Recorded in the rollout JSONL session_meta. import_codex_source() falls back to
# this when the state-db lookup misses, so seeing it means the same-path mount
# is broken.
META_MODEL_KEY = "codex:smoke-codex-meta-model"

ARCHIVE_DAY = "2026-01-02"  # rollout reachable ONLY via the absolute state path
SESSIONS_DAY = "2026-01-01"  # rollout found by the relative sessions/ glob


def day_field(models: dict, model_key: str, day: str, field: str) -> object:
    model = models.get(model_key)
    if not model:
        return "-"
    for row in model.get("daily", []):
        if row["day"] == day:
            return row.get(field, "-")
    return "-"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(f"usage: {sys.argv[0]} <usage.json> <settings.json>")
    usage = json.load(open(sys.argv[1]))
    settings = json.load(open(sys.argv[2]))
    models = {m["model_key"]: m for m in usage.get("models", [])}

    out: list[tuple[str, object]] = [
        ("CODEX_STATE_MODEL", int(STATE_MODEL_KEY in models)),
        ("CODEX_META_MODEL", int(META_MODEL_KEY in models)),
        ("ARCHIVE_INPUT", day_field(models, STATE_MODEL_KEY, ARCHIVE_DAY, "input_tokens")),
        ("ARCHIVE_OUTPUT", day_field(models, STATE_MODEL_KEY, ARCHIVE_DAY, "output_tokens")),
        ("ARCHIVE_REASONING", day_field(models, STATE_MODEL_KEY, ARCHIVE_DAY, "reasoning_output_tokens")),
        ("SESSIONS_INPUT", day_field(models, STATE_MODEL_KEY, SESSIONS_DAY, "input_tokens")),
        ("CLAUDE_INPUT", models.get("claude:smoke-claude-model", {}).get("input_tokens", "-")),
        ("CLAUDE_OUTPUT", models.get("claude:smoke-claude-model", {}).get("output_tokens", "-")),
        ("OPENCODE_INPUT", models.get("opencode:smoke-opencode-model", {}).get("input_tokens", "-")),
        ("OPENCODE_OUTPUT", models.get("opencode:smoke-opencode-model", {}).get("output_tokens", "-")),
    ]

    codex_sources = settings.get("sources", {}).get("codex", [])
    codex = codex_sources[0] if codex_sources else {}
    out += [
        ("CODEX_STATUS", codex.get("status", "-")),
        ("CODEX_FILES", codex.get("file_count", "-")),
        ("CODEX_SOURCE_ERROR", int(bool(codex.get("error")))),
    ]

    for name, value in out:
        print(f"{name}={value}")


if __name__ == "__main__":
    main()
