import datetime as dt
import json
import statistics
import tempfile
import time
import unittest
from pathlib import Path

import codex_usage
import unibase


class CodexDeduplicationBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.codex_root = self.root / ".codex"
        self._write_copied_rollouts(files=12, records=200)

    def _write_copied_rollouts(self, *, files, records):
        base = dt.datetime(2026, 7, 16, 12, tzinfo=dt.timezone.utc)
        rows = []
        cumulative = {key: 0 for key in codex_usage.USAGE_COMPONENTS}
        for index in range(records):
            usage = {
                "input_tokens": 100 + index,
                "cached_input_tokens": 50 + index,
                "output_tokens": 10 + index,
                "reasoning_output_tokens": 5 + index,
            }
            for key in cumulative:
                cumulative[key] += usage[key]
            timestamp = (base + dt.timedelta(seconds=index)).isoformat().replace("+00:00", "Z")
            rows.extend((
                {
                    "timestamp": timestamp,
                    "type": "response_item",
                    "payload": {"type": "message", "role": "assistant"},
                },
                {
                    "timestamp": timestamp,
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "last_token_usage": {**usage, "total_tokens": usage["input_tokens"] + usage["output_tokens"]},
                            "total_token_usage": dict(cumulative),
                        },
                        "rate_limits": {"window": index % 5, "remaining": records - index},
                    },
                },
            ))
        for file_index in range(files):
            path = self.codex_root / "sessions" / str(file_index) / f"rollout-{file_index}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            metadata = {
                "timestamp": "2026-07-16T11:59:00Z",
                "type": "session_meta",
                "payload": {"type": "session_meta", "id": f"session-{file_index}", "model": "gpt-benchmark"},
            }
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in (metadata, *rows)),
                encoding="utf-8",
            )

    def _index_once(self, *, experimental, run):
        database = unibase.Unibase(self.root / f"unibase-{experimental}-{run}.sqlite3")
        database.register_source(unibase.DiscoveredSource(
            "codex-live", "codex", "live", self.codex_root, "live", "Live Codex",
            True, 1000, None, None, "ready",
        ))
        started_at = time.perf_counter()
        result = codex_usage.import_codex_source(
            database,
            database.sources("codex")[0],
            experimental_deduplication=experimental,
            force_full_scan=True,
        )
        return time.perf_counter() - started_at, result

    def test_full_indexing_cost_is_reported_with_and_without_experimental_deduplication(self):
        legacy_samples = []
        experimental_samples = []
        experimental_result = None
        for run in range(3):
            elapsed, _ = self._index_once(experimental=False, run=run)
            legacy_samples.append(elapsed)
            elapsed, experimental_result = self._index_once(experimental=True, run=run)
            experimental_samples.append(elapsed)

        legacy = statistics.median(legacy_samples)
        experimental = statistics.median(experimental_samples)
        delta_percent = ((experimental / legacy) - 1) * 100 if legacy else 0
        print(
            "[MeterMesh benchmark] CODEX full index: "
            f"legacy={legacy * 1000:.1f} ms; experimental={experimental * 1000:.1f} ms; "
            f"delta={delta_percent:+.1f}%"
        )
        self.assertGreater(legacy, 0)
        self.assertGreater(experimental, 0)
        self.assertEqual(experimental_result["token_count_events"], 2400)
        self.assertEqual(experimental_result["unique_usage_records"], 200)


if __name__ == "__main__":
    unittest.main()
