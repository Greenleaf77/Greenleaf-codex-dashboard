import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import claude_usage
import dashboard_api


def assistant_event(event_id, session_id, timestamp, model, *, input_tokens=0, cache_creation=0, cache_read=0, output_tokens=0):
    return {
        "type": "assistant",
        "uuid": event_id,
        "sessionId": session_id,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": "private text is not indexed"}],
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "output_tokens": output_tokens,
            },
        },
    }


def write_rows(path, rows, mode="w"):
    with path.open(mode, encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


class ClaudeUsageIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.projects_path = root / "projects"
        self.projects_path.mkdir()
        self.db_path = root / "claude-usage.sqlite"

    def test_index_is_incremental_and_deduplicates_event_uuids(self):
        project = self.projects_path / "project-a"
        project.mkdir()
        transcript = project / "session.jsonl"
        first = assistant_event(
            "event-1", "session-1", "2026-07-14T12:00:00Z", "claude-sonnet-5",
            input_tokens=10, cache_creation=20, cache_read=30, output_tokens=5,
        )
        second = assistant_event(
            "event-2", "session-1", "2026-07-14T12:01:00Z", "claude-sonnet-5",
            input_tokens=7, cache_read=11, output_tokens=3,
        )
        write_rows(transcript, [first, first, second])

        initial = claude_usage.index_claude_usage(self.projects_path, self.db_path)
        unchanged = claude_usage.index_claude_usage(self.projects_path, self.db_path)

        self.assertEqual(initial["events"], 2)
        self.assertEqual(initial["new_events"], 2)
        self.assertEqual(unchanged["scanned_files"], 0)
        self.assertEqual(unchanged["new_events"], 0)

        third = assistant_event(
            "event-3", "session-2", "2026-07-15T12:00:00Z", "claude-fable-5",
            input_tokens=13, cache_creation=17, cache_read=19, output_tokens=23,
        )
        write_rows(transcript, [third], mode="a")
        appended = claude_usage.index_claude_usage(self.projects_path, self.db_path)
        events = claude_usage.load_claude_events(self.db_path)

        self.assertEqual(appended["scanned_files"], 1)
        self.assertEqual(appended["new_events"], 1)
        self.assertEqual(len(events), 3)
        self.assertEqual(sum(row["input_tokens"] for row in events), 30)
        self.assertEqual(sum(row["cache_creation_input_tokens"] for row in events), 37)
        self.assertEqual(sum(row["cache_read_input_tokens"] for row in events), 60)
        self.assertEqual(sum(row["cached_input_tokens"] for row in events), 97)
        self.assertEqual(sum(row["output_tokens"] for row in events), 31)
        self.assertEqual({row["thread_id"] for row in events}, {"session-1", "session-2"})

    def test_partial_last_line_is_imported_after_it_is_completed(self):
        transcript = self.projects_path / "session.jsonl"
        first = assistant_event("event-1", "session-1", "2026-07-14T12:00:00Z", "claude-sonnet-5", input_tokens=5)
        second = assistant_event("event-2", "session-1", "2026-07-14T12:01:00Z", "claude-sonnet-5", output_tokens=7)
        first_line = (json.dumps(first) + "\n").encode()
        second_line = (json.dumps(second) + "\n").encode()
        split = len(second_line) // 2
        transcript.write_bytes(first_line + second_line[:split])

        initial = claude_usage.index_claude_usage(self.projects_path, self.db_path)
        self.assertEqual(initial["events"], 1)

        with transcript.open("ab") as handle:
            handle.write(second_line[split:])
        completed = claude_usage.index_claude_usage(self.projects_path, self.db_path)

        self.assertEqual(completed["events"], 2)
        self.assertEqual(completed["new_events"], 1)

    def test_dashboard_loads_claude_provider_from_incremental_index(self):
        transcript = self.projects_path / "session.jsonl"
        write_rows(
            transcript,
            [
                assistant_event(
                    "event-1", "session-1", "2026-07-14T12:00:00Z", "claude-sonnet-5",
                    input_tokens=10, cache_creation=20, cache_read=30, output_tokens=5,
                )
            ],
        )
        pricing = {
            "source": "test",
            "url": "",
            "loaded_at": "now",
            "models": dashboard_api.FALLBACK_PRICING,
            "fallback": dashboard_api.FALLBACK_PRICING,
            "error": None,
        }

        with patch.object(dashboard_api, "load_pricing", return_value=pricing):
            data = dashboard_api.load_usage(
                Path("unused.sqlite"),
                "all",
                chart_range="all",
                provider="claude",
                claude_projects_path=self.projects_path,
                claude_db_path=self.db_path,
            )

        self.assertEqual(data["provider"], "claude")
        self.assertEqual(data["provider_label"], "Claude")
        self.assertFalse(data["supports_diagnostics"])
        self.assertEqual(data["totals"]["sessions"], 1)
        self.assertEqual(data["totals"]["input_tokens"], 10)
        self.assertEqual(data["totals"]["cache_creation_input_tokens"], 20)
        self.assertEqual(data["totals"]["cache_read_input_tokens"], 30)
        self.assertEqual(data["totals"]["cached_input_tokens"], 50)
        self.assertEqual(data["totals"]["total_tokens"], 15)
        self.assertEqual(data["totals"]["total_with_cached_tokens"], 65)
        self.assertEqual(data["indexing"]["events"], 1)

        handler = object.__new__(dashboard_api.DashboardHandler)
        filters = handler.filters_from_query("provider=claude&ignore_auto_review=1&include_diagnostics=1")
        self.assertEqual(filters["provider"], "claude")
        self.assertFalse(filters["ignore_auto_review"])
        self.assertFalse(filters["include_diagnostics"])

    def test_removed_transcript_removes_its_indexed_events(self):
        transcript = self.projects_path / "session.jsonl"
        write_rows(
            transcript,
            [assistant_event("event-1", "session-1", "2026-07-14T12:00:00Z", "claude-sonnet-5", input_tokens=5)],
        )
        claude_usage.index_claude_usage(self.projects_path, self.db_path)

        transcript.unlink()
        result = claude_usage.index_claude_usage(self.projects_path, self.db_path)

        self.assertEqual(result["events"], 0)
        self.assertEqual(claude_usage.load_claude_events(self.db_path), [])


if __name__ == "__main__":
    unittest.main()
