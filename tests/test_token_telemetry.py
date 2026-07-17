import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_api


def event(timestamp, item_type, payload):
    return {"timestamp": timestamp, "type": item_type, "payload": payload}


def usage(input_tokens, cached=0, output=0, reasoning=0):
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached,
        "output_tokens": output,
        "reasoning_output_tokens": reasoning,
        "total_tokens": input_tokens + output,
    }


class TokenTelemetryTests(unittest.TestCase):
    def write_rollout(self, rows):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "rollout.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def test_token_count_events_use_last_usage(self):
        first = usage(100, 80, 10, 3)
        second = usage(160, 120, 15, 5)
        reset = usage(20, 8, 4, 1)
        path = self.write_rollout(
            [
                event("2026-07-13T09:00:00Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": first, "total_token_usage": first}}),
                event("2026-07-13T09:01:00Z", "event_msg", {"type": "agent_reasoning"}),
                event("2026-07-13T09:02:00Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": usage(60, 40, 5, 2), "total_token_usage": second}}),
                event("2026-07-13T09:03:00Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": usage(60, 40, 5, 2), "total_token_usage": second}}),
                event("2026-07-13T09:04:00Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": usage(999)}}),
                event("2026-07-14T10:00:00Z", "response_item", {"type": "message", "role": "assistant"}),
                event("2026-07-14T10:01:00Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": reset, "total_token_usage": reset}}),
            ]
        )

        result = dashboard_api.scan_rollout_telemetry(path, "thread-1", "gpt-test")

        self.assertEqual(
            [row["classification"] for row in result["token_events"]],
            ["usage_update"] * 5,
        )
        self.assertEqual([row["raw_input_tokens"] for row in result["usage_events"]], [100, 60, 60, 999, 20])
        filtered = dashboard_api.filter_telemetry_events(result["usage_events"], {"start_day": "2026-07-14", "end_day": "2026-07-14"})
        self.assertEqual([row["raw_input_tokens"] for row in filtered], [20])

    def test_model_output_markers_do_not_change_token_usage(self):
        first = usage(42, 32, 7, 2)
        path = self.write_rollout(
            [
                event("2026-07-14T11:00:00Z", "response_item", {"type": "message", "role": "assistant"}),
                event("2026-07-14T11:00:01Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": first, "total_token_usage": first}}),
            ]
        )

        result = dashboard_api.scan_rollout_telemetry(path, "thread-1", "gpt-test")

        self.assertEqual(result["token_events"][0]["classification"], "usage_update")
        self.assertEqual(result["usage_events"][0]["raw_input_tokens"], 42)

    def test_raw_response_usage_is_ignored_and_rate_limits_affect_dedup_key(self):
        exact = usage(75, 64, 9, 4)
        path = self.write_rollout(
            [
                event("2026-07-14T12:00:00Z", "event_msg", {"type": "raw_response_completed", "response_id": "resp-1", "token_usage": exact}),
                event("2026-07-14T12:00:01Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": exact}, "rate_limits": {"used": 1}}),
                event("2026-07-14T12:00:02Z", "event_msg", {"type": "raw_response_completed", "response_id": "resp-1", "token_usage": exact}),
                event("2026-07-14T12:00:03Z", "event_msg", {"type": "raw_response_completed", "response_id": "resp-2", "token_usage": None}),
                event("2026-07-14T12:00:04Z", "event_msg", {"type": "token_count", "info": {"last_token_usage": exact}, "rate_limits": {"used": 2}}),
            ]
        )

        result = dashboard_api.scan_rollout_telemetry(path, "thread-1", "gpt-test")

        self.assertEqual([row["source"] for row in result["usage_events"]], ["deduplicated", "deduplicated"])
        self.assertEqual([row["raw_input_tokens"] for row in result["usage_events"]], [75, 75])
        self.assertNotEqual(result["usage_events"][0]["dedup_key"], result["usage_events"][1]["dedup_key"])

    def test_diagnostics_are_optional_and_report_local_overcount(self):
        accepted = dashboard_api.usage_event(
            "thread-1", "gpt-5.5", "2026-07-14T12:00:00Z", usage(100, 80, 10, 3), "fallback", "usage_update"
        )
        reported = dashboard_api.usage_event(
            "thread-1", "gpt-5.5", "2026-07-14T12:00:00Z", usage(100, 80, 10, 3), "reported", "usage_update"
        )
        replay = dashboard_api.usage_event(
            "thread-1", "gpt-5.5", "2026-07-14T12:00:01Z", usage(100, 80, 10, 3), "reported", "replayed_event"
        )
        telemetry = {"usage_events": [accepted], "token_events": [reported, replay]}
        pricing = {
            "source": "test",
            "url": "",
            "loaded_at": "now",
            "models": dashboard_api.FALLBACK_PRICING,
            "fallback": dashboard_api.FALLBACK_PRICING,
            "error": None,
        }

        with patch.object(dashboard_api, "scan_token_telemetry", return_value=telemetry), patch.object(
            dashboard_api, "load_pricing", return_value=pricing
        ):
            normal = dashboard_api.load_usage(Path("unused.sqlite"), "all", chart_range="all")
            detailed = dashboard_api.load_usage(Path("unused.sqlite"), "all", chart_range="all", include_diagnostics=True)

        self.assertNotIn("diagnostics", normal)
        summary = detailed["diagnostics"]["summary"]
        self.assertEqual(summary["raw_token_events"], 2)
        self.assertEqual(summary["deduplicated_usage_updates"], 1)
        self.assertEqual(summary["replayed_events"], 1)
        self.assertEqual(summary["estimated_local_overcount_tokens"], 110)
        self.assertEqual(summary["deduplicated_tokens"], detailed["totals"]["total_with_cached_tokens"])
        handler = object.__new__(dashboard_api.DashboardHandler)
        self.assertFalse(handler.filters_from_query("")["include_diagnostics"])
        self.assertTrue(handler.filters_from_query("include_diagnostics=1")["include_diagnostics"])

    def test_chart_aggregates_tokens_with_and_without_cached_input(self):
        filters = dashboard_api.resolve_chart_range("30d", None, None, False)
        filters["start_day"] = "2026-07-15"
        filters["end_day"] = "2026-07-15"
        events = [
            dashboard_api.usage_event(
                "t1", "gpt-a", "2026-07-15T10:00:00Z", usage(100, 80, 10), "exact", "usage_update"
            ),
            dashboard_api.usage_event(
                "t2", "gpt-b", "2026-07-15T11:00:00Z", usage(50, 20, 5), "exact", "usage_update"
            ),
        ]

        chart = dashboard_api.chart_days_from_events(events, filters)

        self.assertEqual(chart["days"][0]["total_tokens"], 65)
        self.assertEqual(chart["days"][0]["total_with_cached_tokens"], 165)
        self.assertEqual(
            {row["model"]: row["total_with_cached_tokens"] for row in chart["days"][0]["models"]},
            {"gpt-a": 110, "gpt-b": 55},
        )
        self.assertEqual(
            {row["model"]: row["total_with_cached_tokens"] for row in chart["models"]},
            {"gpt-a": 110, "gpt-b": 55},
        )


if __name__ == "__main__":
    unittest.main()
