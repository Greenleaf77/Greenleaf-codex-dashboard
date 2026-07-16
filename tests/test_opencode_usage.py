import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import opencode_usage
import unibase


def message_data(*, provider="openai", model="gpt-test", completed=1784203200000, input_tokens=0, output=0, reasoning=0, cache_read=0, cache_write=0, cost=None):
    return {
        "role": "assistant",
        "providerID": provider,
        "modelID": model,
        "time": {"completed": completed, "created": completed - 1000},
        "tokens": {
            "input": input_tokens,
            "output": output,
            "reasoning": reasoning,
            "cache": {"read": cache_read, "write": cache_write},
        },
        "cost": cost,
        "content": "private response text",
        "path": "/private/project",
    }


def create_database(path):
    conn = sqlite3.connect(path)
    conn.execute("pragma journal_mode = wal")
    conn.executescript(
        """
        create table message(
            id text primary key,
            session_id text not null,
            time_created integer not null,
            time_updated integer not null,
            data text not null
        );
        create table session(
            id text primary key,
            title text,
            path text,
            tokens_input integer,
            tokens_output integer,
            tokens_reasoning integer,
            tokens_cache_read integer,
            tokens_cache_write integer,
            cost real
        );
        create table account(id text, email text);
        create table credential(id text, token text);
        create table part(id text, data text);
        """
    )
    return conn


class OpenCodeUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.data_dir = self.root / "opencode"
        self.data_dir.mkdir()
        self.db_path = self.data_dir / "opencode.db"
        self.source_conn = create_database(self.db_path)
        self.addCleanup(self.close_source)
        self.unibase = unibase.Unibase(self.root / "metermesh" / "unibase.sqlite3")
        self.source = unibase.DiscoveredSource(
            "opencode-live", "opencode", "live", self.data_dir, "live", "Live OpenCode",
            True, 1000, None, None, "not_indexed",
        )
        self.unibase.register_source(self.source)

    def close_source(self):
        try:
            self.source_conn.close()
        except sqlite3.Error:
            pass

    def import_source(self):
        return opencode_usage.import_opencode_source(self.unibase, self.unibase.sources("opencode")[0])

    def add_message(self, message_id, data, *, session_id="private-session", updated=1784203200000):
        self.source_conn.execute(
            "insert or replace into message(id, session_id, time_created, time_updated, data) values (?, ?, ?, ?, ?)",
            (message_id, session_id, updated - 1000, updated, json.dumps(data)),
        )
        self.source_conn.commit()

    def test_extracts_usage_and_recorded_cost_without_private_content(self):
        self.add_message("message-1", message_data(input_tokens=10, output=4, reasoning=2, cache_read=3, cache_write=5, cost=0.42))
        self.source_conn.execute("insert into account values ('account-1', 'private@example.test')")
        self.source_conn.execute("insert into credential values ('credential-1', 'secret-token')")
        self.source_conn.execute("insert into part values ('part-1', 'private tool output')")
        self.source_conn.execute("insert into session values ('private-session', 'Private title', '/private/path', 10, 4, 2, 3, 5, 0.42)")
        self.source_conn.commit()

        result = self.import_source()
        event = self.unibase.active_event_rows("opencode")[0]

        self.assertEqual(result["events"], 1)
        self.assertFalse(result["session_aggregate_mismatch"])
        self.assertEqual(event["native_provider_id"], "openai")
        self.assertEqual(event["model"], "gpt-test")
        self.assertEqual(event["input_tokens"], 10)
        self.assertEqual(event["output_tokens"], 4)
        self.assertEqual(event["reasoning_tokens"], 2)
        self.assertEqual(event["cache_read_tokens"], 3)
        self.assertEqual(event["cache_write_tokens"], 5)
        self.assertEqual(event["cost_usd"], 0.42)
        self.assertEqual(event["cost_kind"], "recorded")
        with self.unibase.connect(readonly=True) as conn:
            dump = " ".join(str(value) for row in conn.execute("select * from event_variants") for value in row)
        for secret in ("private response text", "/private/project", "private@example.test", "secret-token", "private tool output", "Private title", "private-session", "message-1"):
            self.assertNotIn(secret, dump)

    def test_committed_wal_row_is_visible_read_only(self):
        self.source_conn.execute("pragma wal_autocheckpoint = 0")
        self.add_message("wal-message", message_data(input_tokens=7))

        self.import_source()

        self.assertEqual(self.unibase.active_event_rows("opencode")[0]["input_tokens"], 7)
        with unibase.open_source_sqlite_readonly(self.db_path) as conn:
            self.assertEqual(conn.execute("pragma query_only").fetchone()[0], 1)

    def test_late_update_and_deletion_reconciliation(self):
        self.add_message("message-1", message_data(input_tokens=5), updated=1784203200000)
        self.add_message("message-2", message_data(input_tokens=6), updated=1784203210000)
        self.import_source()
        self.assertEqual(len(self.unibase.active_event_rows("opencode")), 2)

        self.add_message("message-1", message_data(input_tokens=9), updated=1784203220000)
        self.source_conn.execute("delete from message where id = 'message-2'")
        self.source_conn.commit()
        self.import_source()

        events = self.unibase.active_event_rows("opencode")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["input_tokens"], 9)

    def test_message_that_loses_usage_eligibility_is_removed(self):
        self.add_message("message-1", message_data(input_tokens=5), updated=1784203200000)
        self.import_source()
        self.assertEqual(len(self.unibase.active_event_rows("opencode")), 1)

        ineligible = message_data(input_tokens=0)
        ineligible["role"] = "user"
        self.add_message("message-1", ineligible, updated=1784203220000)
        self.import_source()

        self.assertEqual(self.unibase.active_event_rows("opencode"), [])

    def test_replaced_database_resets_incremental_cursor(self):
        self.add_message("old-message", message_data(input_tokens=5), updated=1784203200000)
        self.import_source()
        self.source_conn.close()
        for path in (self.db_path, Path(str(self.db_path) + "-wal"), Path(str(self.db_path) + "-shm")):
            path.unlink(missing_ok=True)
        self.source_conn = create_database(self.db_path)
        self.add_message("replacement-message", message_data(input_tokens=9), updated=1784203100000)

        self.import_source()

        events = self.unibase.active_event_rows("opencode")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["input_tokens"], 9)

    def test_in_place_replacement_imports_missing_older_messages(self):
        self.add_message("old-message", message_data(input_tokens=5), updated=1784203200000)
        self.import_source()
        self.source_conn.execute("delete from message")
        self.source_conn.commit()
        self.add_message("older-replacement", message_data(input_tokens=7), updated=1784203100000)
        self.add_message("newer-replacement", message_data(input_tokens=9), updated=1784203300000)

        self.import_source()

        self.assertEqual(
            sorted(row["input_tokens"] for row in self.unibase.active_event_rows("opencode")),
            [7, 9],
        )

    def test_incremental_cursor_does_not_store_raw_message_id(self):
        self.add_message("raw-private-message-id", message_data(input_tokens=5))

        self.import_source()

        with self.unibase.connect(readonly=True) as conn:
            cursor = conn.execute("select change_cursor from source_files").fetchone()[0]
        self.assertNotIn("raw-private-message-id", cursor)

    def test_unknown_schema_marks_source_stale_and_retains_committed_data(self):
        self.add_message("message-1", message_data(input_tokens=5))
        self.import_source()
        self.source_conn.close()
        self.source_conn = sqlite3.connect(self.db_path)
        self.source_conn.execute("alter table message rename to message_old")
        self.source_conn.commit()

        with self.assertRaises(RuntimeError):
            self.import_source()

        self.assertEqual(len(self.unibase.active_event_rows("opencode")), 1)
        source_row = self.unibase.sources("opencode")[0]
        self.assertTrue(source_row["stale"])
        self.assertNotIn(str(self.root), source_row["error"])

    def test_resolve_db_precedence(self):
        self.assertEqual(
            opencode_usage.resolve_opencode_db("/tmp/cli.db", {"OPENCODE_USAGE_DB": "/tmp/env.db"}),
            Path("/tmp/cli.db"),
        )
        self.assertEqual(
            opencode_usage.resolve_opencode_db(None, {"OPENCODE_USAGE_DB": "/tmp/env.db"}),
            Path("/tmp/env.db"),
        )


if __name__ == "__main__":
    unittest.main()
