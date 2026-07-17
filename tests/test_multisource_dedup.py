import tempfile
import unittest
from pathlib import Path

import unibase


def source(source_id, kind, priority, snapshot_date=None):
    return unibase.DiscoveredSource(
        source_id=source_id,
        provider="claude",
        kind=kind,
        root_path=Path("/unused"),
        relative_name=source_id,
        label=source_id,
        enabled=True,
        priority=priority,
        snapshot_id=source_id,
        snapshot_date=snapshot_date,
        status="ready",
    )


def event(input_tokens, *, key="event-1"):
    return {
        "provider": "claude",
        "event_key": key,
        "stream_key": "stream-1",
        "timestamp_utc": "2026-07-16T12:00:00Z",
        "occurred_at": 1784203200,
        "model": "claude-test",
        "native_provider_id": "anthropic",
        "semantics": "metadata",
        "classification": "usage_update",
        "input_tokens": input_tokens,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "output_tokens": 1,
        "reasoning_tokens": 0,
        "cost_usd": None,
        "cost_kind": "estimated",
    }


class MultisourceDedupTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db = unibase.Unibase(Path(self.temp_dir.name) / "unibase.sqlite3")

    def test_same_payload_has_one_active_event_and_multiple_occurrences(self):
        self.db.register_source(source("backup-a", "normalized_backup", 500, "2026-07-15T00:00:00Z"))
        self.db.register_source(source("backup-b", "legacy_backup", 400, "2026-07-14T00:00:00Z"))
        variant_a = self.db.add_event("backup-a", None, event(10), 1)
        variant_b = self.db.add_event("backup-b", None, event(10), 1)
        self.db.rebuild_active_events()

        self.assertEqual(variant_a, variant_b)
        self.assertEqual(len(self.db.active_event_rows()), 1)
        with self.db.connect(readonly=True) as conn:
            self.assertEqual(conn.execute("select count(*) from event_occurrences").fetchone()[0], 2)

    def test_conflict_winner_changes_when_higher_priority_source_is_disabled(self):
        self.db.register_source(source("normalized", "normalized_backup", 500, "2026-07-15T00:00:00Z"))
        self.db.register_source(source("legacy", "legacy_backup", 400, "2026-07-16T00:00:00Z"))
        self.db.add_event("normalized", None, event(20), 1)
        self.db.add_event("legacy", None, event(10), 1)
        self.db.rebuild_active_events()
        self.assertEqual(self.db.active_event_rows()[0]["input_tokens"], 20)

        self.db.set_source_enabled("normalized", False)
        self.assertEqual(self.db.active_event_rows()[0]["input_tokens"], 10)

        self.db.set_source_enabled("normalized", True)
        self.assertEqual(self.db.active_event_rows()[0]["input_tokens"], 20)
        with self.db.connect(readonly=True) as conn:
            self.assertEqual(conn.execute("select count(*) from event_variants").fetchone()[0], 2)

    def test_variant_ranking_uses_metadata_from_one_best_source(self):
        self.db.register_source(source("high-old", "normalized_backup", 500, "2026-07-14T00:00:00Z"))
        self.db.register_source(source("high-new", "normalized_backup", 500, "2026-07-15T00:00:00Z"))
        self.db.register_source(source("low-newest", "legacy_backup", 400, "2026-07-16T00:00:00Z"))
        self.db.add_event("high-old", None, event(10), 1)
        self.db.add_event("low-newest", None, event(10), 1)
        self.db.add_event("high-new", None, event(20), 1)

        self.db.rebuild_active_events()

        self.assertEqual(self.db.active_event_rows()[0]["input_tokens"], 20)

    def test_codex_dedup_prefers_known_model_over_unknown_source_variant(self):
        for source_id in ("backup-a", "backup-b"):
            self.db.register_source(unibase.DiscoveredSource(
                source_id, "codex", "legacy_backup", Path("/unused"), source_id, source_id,
                True, 400, source_id, None, "ready",
            ))
        shared = {
            "provider": "codex", "event_key": "dedup-key", "stream_key": "stream-1",
            "timestamp_utc": "2026-07-16T12:00:00Z", "occurred_at": 1784203200,
            "native_provider_id": "openai", "semantics": "codex_global_dedup",
            "classification": "usage_update", "input_tokens": 10, "cache_read_tokens": 20,
            "cache_write_tokens": 0, "output_tokens": 1, "reasoning_tokens": 0,
            "cost_usd": None, "cost_kind": "unavailable",
        }
        self.db.add_event("backup-a", None, {**shared, "model": "(unknown)"}, 2)
        self.db.add_event("backup-b", None, {**shared, "model": "gpt-5.4"}, 1)

        self.db.rebuild_active_events()

        self.assertEqual(self.db.active_event_rows("codex")[0]["model"], "gpt-5.4")

    def test_stale_source_retains_last_committed_projection(self):
        self.db.register_source(source("backup", "normalized_backup", 500))
        self.db.add_event("backup", None, event(10), 1)
        self.db.rebuild_active_events()
        self.db.mark_source_error("backup", RuntimeError("/private/path/source failed"))

        self.assertEqual(len(self.db.active_event_rows()), 1)
        row = self.db.sources()[0]
        self.assertTrue(row["stale"])
        self.assertNotIn("/private/path", row["error"])

    def test_successful_reconciliation_removes_only_missing_source_occurrence(self):
        self.db.register_source(source("backup-a", "normalized_backup", 500))
        self.db.register_source(source("backup-b", "legacy_backup", 400))
        file_a = self.db.upsert_source_file("backup-a", "session.jsonl", "transcript", size=10, mtime_ns=1)
        file_b = self.db.upsert_source_file("backup-b", "session.jsonl", "transcript", size=10, mtime_ns=1)
        self.db.add_event("backup-a", file_a, event(10), 1)
        self.db.add_event("backup-b", file_b, event(10), 1)
        self.db.rebuild_active_events()

        self.db.reconcile_source_files("backup-a", 2, [])

        self.assertEqual(len(self.db.active_event_rows()), 1)
        with self.db.connect(readonly=True) as conn:
            occurrences = conn.execute("select source_id from event_occurrences order by source_id").fetchall()
        self.assertEqual([row[0] for row in occurrences], ["backup-b"])

    def test_provider_prefix_prevents_cross_provider_collisions(self):
        self.db.register_source(source("claude-source", "normalized_backup", 500))
        opencode_source = unibase.DiscoveredSource(
            "opencode-source", "opencode", "normalized_backup", Path("/unused"), "opencode-source",
            "opencode-source", True, 500, None, None, "ready",
        )
        self.db.register_source(opencode_source)
        self.db.add_event("claude-source", None, event(10, key="same-native-id"), 1)
        opencode_event = event(10, key="same-native-id")
        opencode_event["provider"] = "opencode"
        self.db.add_event("opencode-source", None, opencode_event, 1)
        self.db.rebuild_active_events()

        self.assertEqual({row["provider"] for row in self.db.active_event_rows()}, {"claude", "opencode"})


if __name__ == "__main__":
    unittest.main()
