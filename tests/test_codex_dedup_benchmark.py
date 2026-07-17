import datetime as dt
import json
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
        for index in range(records):
            usage = {
                "input_tokens": 100 + index,
                "cached_input_tokens": 50 + index,
                "output_tokens": 10 + index,
                "reasoning_output_tokens": 5 + index,
            }
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
                            "total_token_usage": usage,
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

    def _index_once(self, *, run):
        database = unibase.Unibase(self.root / f"unibase-{run}.sqlite3")
        database.register_source(unibase.DiscoveredSource(
            "codex-live", "codex", "live", self.codex_root, "live", "Live Codex",
            True, 1000, None, None, "ready",
        ))
        started_at = time.perf_counter()
        result = codex_usage.import_codex_source(
            database,
            database.sources("codex")[0],
            force_full_scan=True,
        )
        return time.perf_counter() - started_at, result

    def test_full_deduplicated_indexing_cost_is_reported(self):
        samples = []
        result = None
        for run in range(3):
            elapsed, result = self._index_once(run=run)
            samples.append(elapsed)

        median = sorted(samples)[len(samples) // 2]
        print(
            "[MeterMesh benchmark] CODEX full index: "
            f"deduplicated={median * 1000:.1f} ms"
        )
        self.assertGreater(median, 0)
        self.assertEqual(result["token_count_events"], 2400)
        self.assertEqual(result["unique_usage_records"], 200)


if __name__ == "__main__":
    unittest.main()
