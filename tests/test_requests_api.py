import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_api
import unibase


class RequestsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "unibase.sqlite3"
        self.db = unibase.Unibase(self.path)
        for provider in ("codex", "claude", "opencode"):
            self.db.register_source(unibase.DiscoveredSource(
                f"{provider}-live", provider, "live", Path("/private/source"), "live", f"Live {provider}",
                True, 1000, None, None, "ready",
            ))
        self.pricing = {
            "source": "test", "url": "", "loaded_at": "now",
            "models": dashboard_api.FALLBACK_PRICING,
            "fallback": dashboard_api.FALLBACK_PRICING,
            "error": None,
        }

    def add_event(self, index, timestamp, provider="codex", model="gpt-5.5"):
        parsed = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        self.db.add_event(f"{provider}-live", None, {
            "provider": provider,
            "event_key": f"private-event-{index}",
            "stream_key": f"private-session-{index % 3}",
            "timestamp_utc": timestamp,
            "occurred_at": int(parsed.timestamp()),
            "model": model,
            "native_provider_id": "openai",
            "semantics": "exact" if provider == "codex" else "claude_metadata" if provider == "claude" else "opencode_recorded",
            "classification": "usage_update",
            "input_tokens": index + 1,
            "cache_read_tokens": 2,
            "cache_write_tokens": 3,
            "output_tokens": 4,
            "reasoning_tokens": 1,
            "cost_usd": 0.01 if provider == "opencode" else None,
            "cost_kind": "recorded" if provider == "opencode" else "unavailable",
        }, 1)

    def load(self, **kwargs):
        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing):
            return dashboard_api.load_requests(self.path, **kwargs)

    def test_numbered_pages_and_snapshot_stay_stable_after_append(self):
        for index in range(30):
            self.add_event(index, f"2026-07-16T12:{index:02d}:00Z")
        self.db.rebuild_active_events()
        first = self.load(page=1, page_size=10)
        second = self.load(page=2, page_size=10, snapshot=first["snapshot"])
        first_timestamp = first["items"][0]["timestamp"]

        self.add_event(99, "2026-07-16T13:00:00Z")
        self.db.rebuild_active_events()
        stable = self.load(page=1, page_size=10, snapshot=first["snapshot"])

        self.assertEqual(first["total_pages"], 3)
        self.assertTrue(first["has_next"])
        self.assertTrue(second["has_previous"])
        self.assertEqual(stable["items"][0]["timestamp"], first_timestamp)

    def test_grouped_page_size_counts_branches_without_loading_children(self):
        for minute in range(12):
            self.add_event(minute * 2, f"2026-07-16T12:{minute:02d}:10Z")
            self.add_event(minute * 2 + 1, f"2026-07-16T12:{minute:02d}:40Z", provider="claude")
        self.db.rebuild_active_events()

        payload = self.load(group="1m", page=1, page_size=10)

        self.assertEqual(payload["total_top_level_rows"], 12)
        self.assertEqual(len(payload["items"]), 10)
        self.assertTrue(all(branch["count"] == 2 for branch in payload["items"]))
        self.assertTrue(all(branch["children"] == [] and branch["child_page"] == 0 for branch in payload["items"]))

    def test_grouped_children_use_page_size_and_snapshot(self):
        for index in range(25):
            self.add_event(index, f"2026-07-16T12:{index:02d}:00Z")
        self.db.rebuild_active_events()
        initial = self.load(group="1h", page_size=10)
        bucket = initial["items"][0]["bucket_start"]
        original = dashboard_api._request_item

        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing), patch.object(
            dashboard_api, "_request_item", wraps=original
        ) as request_item:
            second = dashboard_api.load_requests(
                self.path,
                group="1h",
                page_size=10,
                snapshot=initial["snapshot"],
                bucket_start=bucket,
                child_page=2,
            )
        third = self.load(
            group="1h",
            page_size=10,
            snapshot=initial["snapshot"],
            bucket_start=bucket,
            child_page=3,
        )

        self.assertEqual(initial["items"][0]["count"], 25)
        self.assertEqual(initial["items"][0]["child_total_pages"], 3)
        self.assertEqual(len(second["items"][0]["children"]), 10)
        self.assertEqual(second["items"][0]["child_page"], 2)
        self.assertTrue(second["items"][0]["child_has_previous"])
        self.assertTrue(second["items"][0]["child_has_next"])
        self.assertEqual(second["items"][0]["children"][0]["input"], 15)
        self.assertEqual(second["items"][0]["children"][-1]["input"], 6)
        self.assertEqual(len(third["items"][0]["children"]), 5)
        self.assertFalse(third["items"][0]["child_has_next"])
        self.assertEqual(request_item.call_count, 10)

    def test_dst_fall_back_hours_are_distinct(self):
        self.add_event(1, "2026-11-01T05:30:00Z")
        self.add_event(2, "2026-11-01T06:30:00Z")
        self.db.rebuild_active_events()

        payload = self.load(group="1h", page_size=10, timezone_name="America/New_York")

        self.assertEqual(len(payload["items"]), 2)
        self.assertNotEqual(payload["items"][0]["bucket_start"], payload["items"][1]["bucket_start"])

    def test_all_provider_fields_and_privacy(self):
        self.add_event(1, "2026-07-16T12:00:00Z", provider="codex")
        self.add_event(2, "2026-07-16T12:01:00Z", provider="claude")
        self.add_event(3, "2026-07-16T12:02:00Z", provider="opencode")
        self.db.rebuild_active_events()

        payload = self.load(provider="all")
        encoded = json.dumps(payload)

        self.assertEqual({item["provider"] for item in payload["items"]}, {"codex", "claude", "opencode"})
        self.assertTrue(all("cache_read" in item and "cache_write" in item and "cached" in item for item in payload["items"]))
        for forbidden in ("private-event", "private-session", "/private/source", "response_id", "event_key", "stream_key"):
            self.assertNotIn(forbidden, encoded)

    def test_committed_auto_review_preference_filters_requests(self):
        self.add_event(1, "2026-07-16T12:00:00Z")
        self.add_event(2, "2026-07-16T12:01:00Z", model=dashboard_api.AUTO_REVIEW_MODEL)
        self.db.update_settings(1, True)
        self.db.rebuild_active_events()

        payload = self.load()

        self.assertEqual([item["model"] for item in payload["items"]], ["Codex · gpt-5.5"])

    def test_invalid_parameters_and_empty_page(self):
        self.db.rebuild_active_events()
        empty = self.load(page=1, page_size=25)
        self.assertEqual(empty["items"], [])
        self.assertEqual(empty["total_pages"], 1)
        with self.assertRaises(ValueError):
            self.load(group="2h")
        with self.assertRaises(ValueError):
            self.load(page_size=12)
        with self.assertRaises(ValueError):
            self.load(page=0)
        with self.assertRaises(ValueError):
            self.load(child_page=0)
        with self.assertRaises(ValueError):
            self.load(bucket_start="2026-07-16T12:00:00+00:00")

    def test_snapshot_rejects_updates_to_existing_rows(self):
        self.add_event(1, "2026-07-16T12:00:00Z")
        self.db.rebuild_active_events()
        first = self.load(page=1, page_size=10)
        with self.db.connect() as conn:
            conn.execute("update active_events set input_tokens = input_tokens + 1")
            conn.execute("update app_settings set generation = generation + 1 where id = 1")

        with self.assertRaises(dashboard_api.SnapshotConflict):
            self.load(page=1, page_size=10, snapshot=first["snapshot"])

    def test_ungrouped_page_prices_only_requested_rows(self):
        for index in range(100):
            self.add_event(index, f"2026-07-16T{index // 60:02d}:{index % 60:02d}:00Z")
        self.db.rebuild_active_events()
        original = dashboard_api._request_item

        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing), patch.object(
            dashboard_api, "_request_item", wraps=original
        ) as request_item:
            payload = dashboard_api.load_requests(self.path, page=3, page_size=10)

        self.assertEqual(len(payload["items"]), 10)
        self.assertEqual(request_item.call_count, 10)

    def test_page_and_snapshot_use_one_read_transaction(self):
        self.add_event(1, "2026-07-16T12:00:00Z")
        self.db.rebuild_active_events()
        original_digest = dashboard_api._requests_snapshot_digest
        updated = False

        def update_after_digest(rows):
            nonlocal updated
            buffered = list(rows)
            digest = original_digest(buffered)
            if not updated:
                updated = True
                with self.db.connect() as conn:
                    conn.execute("update active_events set input_tokens = input_tokens + 100")
            return digest

        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing), patch.object(
            dashboard_api, "_requests_snapshot_digest", side_effect=update_after_digest
        ):
            payload = dashboard_api.load_requests(self.path, page=1, page_size=10)

        self.assertEqual(payload["items"][0]["input"], 2)
        with self.assertRaises(dashboard_api.SnapshotConflict):
            self.load(page=1, page_size=10, snapshot=payload["snapshot"])


if __name__ == "__main__":
    unittest.main()
