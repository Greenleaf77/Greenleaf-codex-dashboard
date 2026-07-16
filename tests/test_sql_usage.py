import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_api
import unibase


def round_floats(value):
    if isinstance(value, float):
        return round(value, 12)
    if isinstance(value, list):
        return [round_floats(item) for item in value]
    if isinstance(value, dict):
        return {key: round_floats(item) for key, item in value.items()}
    return value


class SqlUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "unibase.sqlite3"
        self.db = unibase.Unibase(self.path)
        for provider in ("codex", "claude", "opencode"):
            self.db.register_source(unibase.DiscoveredSource(
                f"{provider}-live", provider, "live", Path("/unused"), "live", f"Live {provider}",
                True, 1000, None, None, "ready",
            ))
        self.pricing = {
            "source": "test",
            "url": "",
            "loaded_at": "now",
            "models": {},
            "fallback": dashboard_api.FALLBACK_PRICING,
            "error": None,
        }

    def add_event(
        self,
        provider,
        event_key,
        stream_key,
        timestamp,
        model,
        *,
        native_provider_id=None,
        input_tokens=0,
        cache_read=0,
        cache_write=0,
        output_tokens=0,
        reasoning_tokens=0,
        cost_usd=None,
        cost_kind="unavailable",
        semantics="exact",
        classification="usage_update",
    ):
        occurred_at = int(dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp())
        self.db.add_event(f"{provider}-live", None, {
            "provider": provider,
            "event_key": event_key,
            "stream_key": stream_key,
            "timestamp_utc": timestamp,
            "occurred_at": occurred_at,
            "model": model,
            "native_provider_id": native_provider_id,
            "semantics": semantics,
            "classification": classification,
            "input_tokens": input_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "cost_usd": cost_usd,
            "cost_kind": cost_kind,
        }, 1)

    def python_reference(self):
        timezone = dashboard_api.resolve_timezone("America/New_York")
        filters = dashboard_api.resolve_range("custom", "2026-07-14", "2026-07-16", True)
        chart_filters = dashboard_api.resolve_chart_range("custom", "2026-07-14", "2026-07-16", True)
        events = []
        missing_models = set()
        for row in self.db.active_event_rows("all"):
            event, missing = dashboard_api.event_from_active_row(row, timezone, True, self.pricing)
            if row["provider"] == "codex" and row["model"] == dashboard_api.AUTO_REVIEW_MODEL:
                continue
            if missing:
                missing_models.add(missing)
            events.append(event)
        selected = dashboard_api.filter_telemetry_events(events, filters)
        chart_events = dashboard_api.filter_telemetry_events(events, chart_filters)
        daily, models = dashboard_api._aggregate_rows(selected)
        days = {row["day"] for row in daily}
        peak = max(daily, key=lambda row: row["total_tokens"], default=None)
        totals = {key: sum(row[key] for row in daily) for key in dashboard_api.AGGREGATE_KEYS}
        totals["sessions"] = len({event["thread_id"] for event in selected})
        totals["active_days"] = len(days)
        provider_breakdown = {}
        for provider in ("codex", "claude", "opencode"):
            provider_events = [event for event in selected if event["provider"] == provider]
            provider_breakdown[provider] = {
                "events": len(provider_events),
                "sessions": len({event["thread_id"] for event in provider_events}),
                "total_tokens": sum(event["total_tokens"] for event in provider_events),
                "total_with_cached_tokens": sum(event["total_with_cached_tokens"] for event in provider_events),
                "cost": {
                    "recorded": sum(event["cost_usd"] for event in provider_events if event["cost_kind"] == "recorded"),
                    "estimated": sum(event["cost_usd"] for event in provider_events if event["cost_kind"] == "estimated"),
                    "unavailable": sum(event["cost_kind"] == "unavailable" for event in provider_events),
                },
            }
        return {
            "totals": totals,
            "cost": {
                "recorded": sum(event["cost_usd"] for event in selected if event["cost_kind"] == "recorded"),
                "estimated": sum(event["cost_usd"] for event in selected if event["cost_kind"] == "estimated"),
                "unavailable": sum(event["cost_kind"] == "unavailable" for event in selected),
            },
            "provider_breakdown": provider_breakdown,
            "daily": daily,
            "models": models,
            "chart": dashboard_api.chart_days_from_events(chart_events, chart_filters),
            "pricing_missing": sorted(missing_models),
            "favorite_model": models[0]["model"] if models else "-",
            "current_streak": dashboard_api.current_streak(days),
            "longest_streak": dashboard_api.longest_streak(days),
            "peak_day": peak["day"] if peak else "-",
            "peak_day_tokens": peak["total_tokens"] if peak else 0,
        }

    def test_sql_usage_matches_python_aggregation(self):
        self.add_event(
            "codex", "c1", "shared", "2026-07-15T03:30:00Z", "gpt-5.5",
            native_provider_id="openai", input_tokens=10, cache_read=3, output_tokens=2,
        )
        self.add_event(
            "codex", "c2", "shared", "2026-07-15T15:30:00Z", "gpt-5.5",
            native_provider_id="azure", input_tokens=20, cache_write=4, output_tokens=5,
        )
        self.add_event(
            "claude", "a1", "shared", "2026-07-16T02:00:00Z", "claude-sonnet-4-6",
            input_tokens=30, cache_read=6, cache_write=7, output_tokens=8,
            semantics="claude_metadata", classification="counter_reset",
        )
        self.add_event(
            "opencode", "o1", "open", "2026-07-16T18:00:00Z", "gpt-5.5",
            input_tokens=40, output_tokens=9, cost_usd=0.25, cost_kind="recorded",
            semantics="opencode_recorded",
        )
        self.add_event(
            "opencode", "o2", "unknown", "2026-07-16T19:00:00Z", "unknown-model",
            input_tokens=50, output_tokens=10,
        )
        self.add_event(
            "codex", "auto", "auto", "2026-07-16T20:00:00Z", dashboard_api.AUTO_REVIEW_MODEL,
            input_tokens=999, output_tokens=999,
        )
        self.db.rebuild_active_events()

        expected = self.python_reference()
        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing), patch.object(
            unibase.Unibase, "active_event_rows", side_effect=AssertionError("materialized active events")
        ):
            actual = dashboard_api.load_unibase_usage(
                self.path,
                "custom",
                "2026-07-14",
                "2026-07-16",
                True,
                "custom",
                "2026-07-14",
                "2026-07-16",
                include_diagnostics=True,
                provider="all",
                timezone_name="America/New_York",
            )

        actual_subset = {
            "totals": actual["totals"],
            "cost": actual["cost"],
            "provider_breakdown": actual["provider_breakdown"],
            "daily": actual["daily"],
            "models": actual["models"],
            "chart": actual["chart"],
            "pricing_missing": actual["pricing"]["missing_models"],
            "favorite_model": actual["favorite_model"],
            "current_streak": actual["current_streak"],
            "longest_streak": actual["longest_streak"],
            "peak_day": actual["peak_day"],
            "peak_day_tokens": actual["peak_day_tokens"],
        }
        self.assertEqual(round_floats(actual_subset), round_floats(expected))
        self.assertEqual(actual["diagnostics"]["summary"]["deduplicated_usage_updates"], 5)
        self.assertEqual(actual["diagnostics"]["summary"]["counter_resets"], 1)
        self.assertEqual(
            actual["diagnostics"]["summary"]["deduplicated_tokens"],
            actual["totals"]["total_with_cached_tokens"],
        )

    def test_dst_range_uses_exact_local_day_boundaries(self):
        self.add_event(
            "codex", "before", "s1", "2026-03-08T04:30:00Z", "gpt-5.5",
            input_tokens=100,
        )
        self.add_event(
            "codex", "inside", "s2", "2026-03-08T05:30:00Z", "gpt-5.5",
            input_tokens=20,
        )
        self.add_event(
            "codex", "after-jump", "s3", "2026-03-08T07:30:00Z", "gpt-5.5",
            input_tokens=30,
        )
        self.db.rebuild_active_events()

        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing):
            data = dashboard_api.load_unibase_usage(
                self.path,
                "custom",
                "2026-03-08",
                "2026-03-08",
                False,
                "custom",
                "2026-03-08",
                "2026-03-08",
                provider="codex",
                timezone_name="America/New_York",
            )

        self.assertEqual(data["totals"]["input_tokens"], 50)
        self.assertEqual([row["day"] for row in data["daily"]], ["2026-03-08"])

    def test_all_provider_range_uses_time_index(self):
        with self.db.connect(readonly=True) as conn:
            plan = " ".join(
                str(row["detail"])
                for row in conn.execute(
                    "explain query plan select * from active_events where occurred_at >= ? and occurred_at < ?",
                    (1, 2),
                )
            )
        self.assertIn("active_events_time", plan)


if __name__ == "__main__":
    unittest.main()
