import json
import tempfile
import unittest
from pathlib import Path

import codex_usage
import dashboard_api
import unibase


def usage(input_tokens, cached=0, output=0, reasoning=0):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output,
        "reasoning_output_tokens": reasoning,
    }


def session_meta(session_id, model="gpt-test"):
    return {"timestamp": "2026-07-16T11:59:00Z", "type": "session_meta", "payload": {"type": "session_meta", "id": session_id, "model": model}}


def exact(timestamp, response_id, token_usage):
    return {"timestamp": timestamp, "type": "event_msg", "payload": {"type": "raw_response_completed", "response_id": response_id, "token_usage": token_usage}}


def token(timestamp, last, total):
    return {"timestamp": timestamp, "type": "event_msg", "payload": {"type": "token_count", "info": {"last_token_usage": last, "total_token_usage": total}}}


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class CodexUsageAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.codex_root = self.root / ".codex"
        self.unibase = unibase.Unibase(self.root / "metermesh" / "unibase.sqlite3")
        self.source = unibase.DiscoveredSource(
            "codex-live", "codex", "live", self.codex_root, "live", "Live Codex",
            True, 1000, None, None, "not_indexed",
        )
        self.unibase.register_source(self.source)

    def import_source(self):
        return codex_usage.import_codex_source(self.unibase, self.unibase.sources("codex")[0])

    def test_identical_and_prefix_copies_are_consolidated(self):
        first = [session_meta("session-1"), exact("2026-07-16T12:00:00Z", "response-1", usage(10, 2, 3))]
        write_rows(self.codex_root / "sessions" / "a" / "rollout-a.jsonl", first)
        write_rows(self.codex_root / "sessions" / "b" / "rollout-b.jsonl", first + [exact("2026-07-16T12:01:00Z", "response-2", usage(20, 4, 5))])

        result = self.import_source()
        events = self.unibase.active_event_rows("codex")

        self.assertEqual(result["events"], 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(sum(row["input_tokens"] for row in events), 24)
        with self.unibase.connect(readonly=True) as conn:
            self.assertEqual(conn.execute("select count(*) from event_occurrences").fetchone()[0], 3)

    def test_exact_and_fallback_reconstruction_matches_existing_algorithm(self):
        rows = [
            session_meta("session-1"),
            exact("2026-07-16T12:00:00Z", "response-1", usage(10, 2, 3)),
            token("2026-07-16T12:00:01Z", usage(10, 2, 3), usage(10, 2, 3)),
            {"timestamp": "2026-07-16T12:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant"}},
            token("2026-07-16T12:00:03Z", usage(5, 1, 2), usage(15, 3, 5)),
        ]
        path = self.codex_root / "sessions" / "a" / "rollout-a.jsonl"
        write_rows(path, rows)

        old = dashboard_api.scan_rollout_telemetry(path, "thread", "gpt-test")["usage_events"]
        new = codex_usage.scan_rollout_telemetry(path, "thread", "gpt-test")["usage_events"]

        self.assertEqual([row["source"] for row in new], [row["source"] for row in old])
        self.assertEqual([row["input_tokens"] for row in new], [row["input_tokens"] for row in old])
        self.assertEqual([row["cache_read_tokens"] for row in new], [row["cache_read_input_tokens"] for row in old])

    def test_subagent_session_identity_is_not_parent_identity(self):
        write_rows(self.codex_root / "sessions" / "parent" / "rollout-parent.jsonl", [session_meta("parent"), exact("2026-07-16T12:00:00Z", "p-response", usage(5))])
        write_rows(self.codex_root / "sessions" / "child" / "rollout-child.jsonl", [session_meta("child"), exact("2026-07-16T12:01:00Z", "c-response", usage(7))])

        self.import_source()

        self.assertEqual(len({row["stream_key"] for row in self.unibase.active_event_rows("codex")}), 2)

    def test_source_file_registry_does_not_store_rollout_names(self):
        path = self.codex_root / "sessions" / "private-project" / "rollout-private-session-uuid.jsonl"
        write_rows(path, [session_meta("private-session"), exact("2026-07-16T12:00:00Z", "private-response", usage(5))])

        self.import_source()

        with self.unibase.connect(readonly=True) as conn:
            stored = " ".join(row[0] for row in conn.execute("select relative_path from source_files"))
        self.assertNotIn("private-project", stored)
        self.assertNotIn("private-session", stored)
        self.assertNotIn("rollout-", stored)

    def test_changed_rollout_reconciles_old_occurrences(self):
        path = self.codex_root / "sessions" / "a" / "rollout-a.jsonl"
        write_rows(path, [session_meta("session-1"), exact("2026-07-16T12:00:00Z", "response-1", usage(5))])
        self.import_source()
        write_rows(path, [session_meta("session-1"), exact("2026-07-16T12:00:00Z", "response-2", usage(9))])

        self.import_source()

        events = self.unibase.active_event_rows("codex")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["input_tokens"], 9)

    def test_windows_filename_uuid_fallback(self):
        path = self.root / "folder\\rollout-2026-07-16T00-00-00-123e4567-e89b-12d3-a456-426614174000.jsonl"
        write_rows(path, [exact("2026-07-16T12:00:00Z", "response-1", usage(5))])
        stream_key, _ = codex_usage.rollout_metadata(path, "hash")
        expected = unibase.stable_id("codex", "stream", "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(stream_key, expected)


if __name__ == "__main__":
    unittest.main()
