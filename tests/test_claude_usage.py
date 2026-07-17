import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import claude_usage
import dashboard_api
import unibase


def assistant_event(event_id, session_id, timestamp, model, *, input_tokens=0, cache_creation=0, cache_read=0, output_tokens=0):
    event = {
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
    return event


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


class ClaudeUnibaseAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.source_root = root / ".claude"
        self.projects_path = self.source_root / "projects"
        self.projects_path.mkdir(parents=True)
        self.unibase_path = root / "metermesh" / "unibase.sqlite3"
        self.unibase = unibase.Unibase(self.unibase_path)
        self.source = unibase.DiscoveredSource(
            "claude-live", "claude", "live", self.source_root, "live", "Live Claude",
            True, 1000, None, None, "not_indexed",
        )
        self.unibase.register_source(self.source)

    def import_source(self):
        return claude_usage.import_claude_source(self.unibase, self.unibase.sources("claude")[0])

    def test_deduplicates_uuid_across_files_and_does_not_store_content(self):
        project = self.projects_path / "opaque"
        project.mkdir()
        row = assistant_event(
            "same-event", "private-session", "2026-07-16T12:00:00Z", "claude-sonnet-5",
            input_tokens=10, cache_creation=2, cache_read=3, output_tokens=4,
        )
        write_rows(project / "primary.jsonl", [row])
        subagents = project / "subagents"
        subagents.mkdir()
        write_rows(subagents / "child.jsonl", [row])

        result = self.import_source()
        events = self.unibase.active_event_rows("claude")

        self.assertEqual(result["events"], 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["cache_write_tokens"], 2)
        self.assertEqual(events[0]["cache_read_tokens"], 3)
        with self.unibase.connect(readonly=True) as conn:
            dump = " ".join(str(value) for row in conn.execute("select * from event_variants") for value in row)
        self.assertNotIn("private text is not indexed", dump)
        self.assertNotIn("private-session", dump)
        self.assertNotIn("same-event", dump)

    def test_idless_fallback_is_source_independent(self):
        row = assistant_event("", "session-1", "2026-07-16T12:00:00Z", "claude-sonnet-5", input_tokens=8)
        project_a = self.projects_path / "a"
        project_b = self.projects_path / "b"
        project_a.mkdir()
        project_b.mkdir()
        write_rows(project_a / "one.jsonl", [row])
        write_rows(project_b / "two.jsonl", [row])

        self.import_source()

        self.assertEqual(len(self.unibase.active_event_rows("claude")), 1)

    def test_source_file_registry_does_not_store_project_or_transcript_names(self):
        project = self.projects_path / "private-project-name"
        project.mkdir()
        row = assistant_event(
            "private-message", "private-session", "2026-07-16T12:00:00Z", "claude-sonnet-5",
            input_tokens=5,
        )
        write_rows(project / "private-session-uuid.jsonl", [row])

        self.import_source()

        with self.unibase.connect(readonly=True) as conn:
            stored = " ".join(row[0] for row in conn.execute("select relative_path from source_files"))
        self.assertNotIn("private-project-name", stored)
        self.assertNotIn("private-session", stored)

    def test_append_partial_replace_and_delete_reconcile(self):
        transcript = self.projects_path / "session.jsonl"
        first = assistant_event("event-1", "session-1", "2026-07-16T12:00:00Z", "claude-sonnet-5", input_tokens=5)
        second = assistant_event("event-2", "session-1", "2026-07-16T12:01:00Z", "claude-sonnet-5", output_tokens=7)
        first_line = (json.dumps(first) + "\n").encode()
        second_line = (json.dumps(second) + "\n").encode()
        split = len(second_line) // 2
        transcript.write_bytes(first_line + second_line[:split])

        initial = self.import_source()
        self.assertEqual(initial["events"], 1)
        with transcript.open("ab") as handle:
            handle.write(second_line[split:])
        appended = self.import_source()
        self.assertEqual(appended["events"], 2)

        replacement = assistant_event("event-3", "session-2", "2026-07-16T13:00:00Z", "claude-fable-5", input_tokens=11)
        transcript.write_text(json.dumps(replacement) + "\n", encoding="utf-8")
        replaced = self.import_source()
        self.assertEqual(replaced["events"], 1)
        self.assertEqual(self.unibase.active_event_rows("claude")[0]["input_tokens"], 11)

        transcript.unlink()
        removed = self.import_source()
        self.assertEqual(removed["events"], 0)

    def test_normal_refresh_reconciles_deletions_retained_by_resync(self):
        transcript = self.projects_path / "session.jsonl"
        first = assistant_event("event-1", "session-1", "2026-07-16T12:00:00Z", "claude-sonnet-5", input_tokens=5)
        second = assistant_event("event-2", "session-1", "2026-07-16T12:01:00Z", "claude-sonnet-5", input_tokens=7)
        write_rows(transcript, [first, second])
        self.import_source()
        transcript.write_text(json.dumps(first) + "\n", encoding="utf-8")

        claude_usage.import_claude_source(
            self.unibase,
            self.unibase.sources("claude")[0],
            force_full_scan=True,
            non_destructive=True,
        )

        self.assertEqual(len(self.unibase.active_event_rows("claude")), 2)
        self.assertTrue(self.unibase.sources("claude")[0]["stale"])
        with patch.object(dashboard_api, "register_default_sources"):
            dashboard_api.refresh_enabled_sources(self.unibase_path)
        self.assertEqual(len(self.unibase.active_event_rows("claude")), 1)
        self.assertFalse(self.unibase.sources("claude")[0]["stale"])


if __name__ == "__main__":
    unittest.main()
