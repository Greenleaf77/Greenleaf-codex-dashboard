import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard_api
import unibase


class AllProviderTests(unittest.TestCase):
    def setUp(self):
        dashboard_api.USAGE_RESPONSE_CACHE.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "unibase.sqlite3"
        self.db = unibase.Unibase(self.path)
        for provider in ("codex", "claude", "opencode"):
            self.db.register_source(unibase.DiscoveredSource(
                f"{provider}-live", provider, "live", Path("/unused"), "live", f"Live {provider}",
                True, 1000, None, None, "ready",
            ))
        self.add_event("codex", 10, 2, 0, 4, None, "unavailable")
        self.add_event("claude", 20, 3, 5, 6, None, "unavailable")
        self.add_event("opencode", 30, 7, 11, 8, 0.5, "recorded")
        self.db.rebuild_active_events()
        self.pricing = {
            "source": "test", "url": "", "loaded_at": "now",
            "models": dashboard_api.FALLBACK_PRICING,
            "fallback": dashboard_api.FALLBACK_PRICING,
            "error": None,
        }

    def add_event(
        self,
        provider,
        input_tokens,
        cache_read,
        cache_write,
        output,
        cost,
        cost_kind,
        *,
        event_key="same-native-id",
    ):
        self.db.add_event(f"{provider}-live", None, {
            "provider": provider,
            "event_key": event_key,
            "stream_key": "same-session-id",
            "timestamp_utc": "2026-07-16T12:00:00Z",
            "occurred_at": 1784203200,
            "model": "gpt-5.5",
            "native_provider_id": "same-provider-id",
            "semantics": "opencode_recorded" if provider == "opencode" else "claude_metadata" if provider == "claude" else "exact",
            "classification": "usage_update",
            "input_tokens": input_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "output_tokens": output,
            "reasoning_tokens": 0,
            "cost_usd": cost,
            "cost_kind": cost_kind,
        }, 1)

    def load(self, provider="all"):
        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing):
            return dashboard_api.load_unibase_usage(self.path, "all", chart_range="all", provider=provider)

    def test_all_equals_provider_sum_without_cross_provider_collisions(self):
        all_data = self.load("all")
        scopes = [self.load(provider) for provider in ("codex", "claude", "opencode")]

        self.assertEqual(all_data["totals"]["total_tokens"], sum(scope["totals"]["total_tokens"] for scope in scopes))
        self.assertEqual(all_data["totals"]["total_with_cached_tokens"], sum(scope["totals"]["total_with_cached_tokens"] for scope in scopes))
        self.assertEqual(all_data["totals"]["sessions"], 3)
        self.assertEqual(len(all_data["models"]), 3)
        self.assertEqual({row["model"] for row in all_data["models"]}, {"Codex · gpt-5.5", "Claude · gpt-5.5", "OpenCode · gpt-5.5"})
        self.assertEqual(all_data["activity"]["total_seconds"], 10 * 60)
        self.assertEqual(sum(scope["activity"]["total_seconds"] for scope in scopes), 30 * 60)
        self.assertEqual(all_data["cost"]["recorded"], 0.5)
        self.assertGreater(all_data["cost"]["estimated"], 0)

    def test_all_can_merge_matching_models_across_providers(self):
        with self.db.connect() as conn:
            conn.execute("update app_settings set merge_models_across_providers = 1")

        data = self.load("all")

        self.assertTrue(data["merge_models_across_providers"])
        self.assertEqual(len(data["models"]), 1)
        model = data["models"][0]
        self.assertEqual(model["model"], "gpt-5.5")
        self.assertEqual(model["model_key"], "gpt-5.5")
        self.assertEqual(model["provider"], "all")
        self.assertEqual(model["sessions"], 3)
        self.assertEqual(model["total_tokens"], data["totals"]["total_tokens"])
        self.assertEqual([row["model"] for row in data["chart"]["models"]], ["gpt-5.5"])
        self.assertEqual([row["model"] for row in data["chart"]["days"][0]["models"]], ["gpt-5.5"])

    def test_opencode_endpoints_share_one_model_row(self):
        self.db.add_event("opencode-live", None, {
            "provider": "opencode",
            "event_key": "second-endpoint-event",
            "stream_key": "second-endpoint-session",
            "timestamp_utc": "2026-07-16T13:00:00Z",
            "occurred_at": 1784206800,
            "model": "gpt-5.5",
            "native_provider_id": "second-endpoint",
            "semantics": "opencode_recorded",
            "classification": "usage_update",
            "input_tokens": 10,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": 3,
            "reasoning_tokens": 0,
            "cost_usd": 0.25,
            "cost_kind": "recorded",
        }, 1)
        self.db.rebuild_active_events()

        opencode = self.load("opencode")
        self.assertEqual(len(opencode["models"]), 1)
        model = opencode["models"][0]
        self.assertEqual(model["model"], "gpt-5.5")
        self.assertEqual(model["model_key"], "opencode:gpt-5.5")
        self.assertEqual(model["sessions"], 2)
        self.assertEqual(model["input_tokens"], 40)
        self.assertEqual(model["output_tokens"], 11)
        self.assertEqual(model["cost_usd"], 0.75)

        all_data = self.load("all")
        self.assertEqual(len(all_data["models"]), 3)
        self.assertEqual(sum(row["model"] == "OpenCode · gpt-5.5" for row in all_data["models"]), 1)

    def test_missing_and_invalid_provider_default_to_all(self):
        self.assertEqual(dashboard_api.normalize_provider(None), "all")
        self.assertEqual(dashboard_api.normalize_provider("invalid"), "all")
        handler = object.__new__(dashboard_api.DashboardHandler)
        handler.unibase_path = self.path
        self.assertEqual(handler.filters_from_query("")["provider"], "all")
        self.assertEqual(handler.filters_from_query("provider=invalid")["provider"], "all")

    def test_chart_range_is_independent_from_global_range(self):
        handler = object.__new__(dashboard_api.DashboardHandler)
        handler.unibase_path = self.path
        filters = handler.filters_from_query("range=7d&chart_range=all")
        self.assertEqual(filters["chart_range"], "all")
        self.assertIsNone(filters["chart_start_day"])
        self.assertIsNone(filters["chart_end_day"])

        custom = handler.filters_from_query(
            "range=custom&start=2026-07-10&end=2026-07-12&chart_range=custom&chart_start=2020-01-01&chart_end=2020-01-02"
        )
        self.assertEqual(custom["chart_range"], "custom")
        self.assertEqual(custom["chart_start_day"], "2020-01-01")
        self.assertEqual(custom["chart_end_day"], "2020-01-02")

    def test_chart_granularity_uses_requested_boundaries(self):
        self.assertEqual(dashboard_api.chart_granularity(
            dashboard_api.dt.date(2026, 1, 1), dashboard_api.dt.date(2026, 3, 31)
        ), "day")
        self.assertEqual(dashboard_api.chart_granularity(
            dashboard_api.dt.date(2026, 1, 1), dashboard_api.dt.date(2026, 4, 1)
        ), "week")
        self.assertEqual(dashboard_api.chart_granularity(
            dashboard_api.dt.date(2026, 1, 16), dashboard_api.dt.date(2026, 7, 16)
        ), "week")
        self.assertEqual(dashboard_api.chart_granularity(
            dashboard_api.dt.date(2026, 1, 16), dashboard_api.dt.date(2026, 7, 17)
        ), "month")
        timezone_day = dashboard_api.resolve_chart_range(
            "1d", today=dashboard_api.dt.date(2026, 7, 17)
        )
        self.assertEqual(timezone_day["start_day"], "2026-07-17")
        self.assertEqual(timezone_day["end_day"], "2026-07-17")
        for range_name, expected_start in (("3d", "2026-07-15"), ("14d", "2026-07-04"), ("21d", "2026-06-27")):
            resolved = dashboard_api.resolve_chart_range(range_name, today=dashboard_api.dt.date(2026, 7, 17))
            self.assertEqual(resolved["start_day"], expected_start)
            self.assertEqual(resolved["end_day"], "2026-07-17")

    def test_production_usage_payload_does_not_call_provider_scanners(self):
        handler = object.__new__(dashboard_api.DashboardHandler)
        handler.unibase_path = self.path
        source_root = Path(self.temp_dir.name) / "sources"
        handler.db_path = source_root / ".codex" / "state_5.sqlite"
        handler.claude_projects_path = source_root / ".claude" / "projects"
        handler.opencode_db_path = source_root / "opencode" / "opencode.db"
        filters = handler.filters_from_query("provider=all&range=all&chart_range=all")
        with patch.object(dashboard_api, "scan_token_telemetry", side_effect=AssertionError("scanner called")), patch.object(
            dashboard_api, "index_claude_usage", side_effect=AssertionError("scanner called")
        ), patch.object(dashboard_api, "schedule_enabled_sources_refresh"), patch.object(
            dashboard_api, "load_pricing", return_value=self.pricing
        ):
            payload = handler.usage_payload(filters)
        self.assertEqual(payload["provider"], "all")

    def test_production_usage_payload_reads_committed_generation_without_waiting(self):
        handler = object.__new__(dashboard_api.DashboardHandler)
        handler.unibase_path = self.path
        source_root = Path(self.temp_dir.name) / "sources"
        handler.db_path = source_root / ".codex" / "state_5.sqlite"
        handler.claude_projects_path = source_root / ".claude" / "projects"
        handler.opencode_db_path = source_root / "opencode" / "opencode.db"
        filters = handler.filters_from_query("provider=all&range=all&chart_range=all")
        with patch.object(dashboard_api, "schedule_enabled_sources_refresh") as refresh, patch.object(
            dashboard_api, "load_pricing", return_value=self.pricing
        ):
            payload = handler.usage_payload(filters)
        refresh.assert_not_called()
        self.assertEqual(payload["sync"]["state"], "idle")

    def test_production_usage_payload_reuses_generation_cache(self):
        handler = object.__new__(dashboard_api.DashboardHandler)
        handler.unibase_path = self.path
        source_root = Path(self.temp_dir.name) / "sources"
        handler.db_path = source_root / ".codex" / "state_5.sqlite"
        handler.claude_projects_path = source_root / ".claude" / "projects"
        handler.opencode_db_path = source_root / "opencode" / "opencode.db"
        filters = handler.filters_from_query("provider=all&range=all&chart_range=all")

        with patch.object(dashboard_api, "load_pricing", return_value=self.pricing), patch.object(
            dashboard_api, "load_unibase_usage", wraps=dashboard_api.load_unibase_usage
        ) as load_usage:
            first = handler.usage_payload(filters)
            second = handler.usage_payload(filters)

        self.assertEqual(first["generation"], second["generation"])
        self.assertEqual(load_usage.call_count, 1)

    def test_cache_alias_does_not_double_count(self):
        data = self.load("all")
        totals = data["totals"]
        self.assertEqual(totals["cached_input_tokens"], totals["cache_read_input_tokens"] + totals["cache_creation_input_tokens"])
        self.assertEqual(totals["total_with_cached_tokens"], totals["total_tokens"] + totals["cached_input_tokens"])

if __name__ == "__main__":
    unittest.main()
