import datetime as dt
import unittest

import dashboard_api


class ActivityTimeTests(unittest.TestCase):
    timezone = dashboard_api.resolve_timezone("UTC")

    def timestamp(self, value: str) -> int:
        return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())

    def activity(self, timestamps, start="2026-07-16", end="2026-07-16"):
        filters = dashboard_api.resolve_chart_range("custom", start, end, today=dt.date.fromisoformat(end))
        return dashboard_api.activity_from_timestamps(
            [self.timestamp(value) for value in timestamps], filters, self.timezone
        )

    def test_merges_nearby_requests_and_starts_a_new_block_after_timeout(self):
        activity = self.activity([
            "2026-07-16T09:00:00Z",
            "2026-07-16T09:05:00Z",
            "2026-07-16T09:30:00Z",
        ])

        self.assertEqual(activity["total_seconds"], 25 * 60)
        self.assertEqual(activity["focus_blocks"], 2)
        self.assertEqual(activity["request_count"], 3)
        self.assertEqual(activity["days"][0]["active_seconds"], 25 * 60)

    def test_single_request_gets_one_inactivity_window(self):
        activity = self.activity(["2026-07-16T12:00:00Z"])

        self.assertEqual(activity["total_seconds"], 10 * 60)
        self.assertEqual(activity["average_seconds_per_day"], 10 * 60)
        self.assertEqual(activity["period_days"], 1)
        self.assertEqual(activity["active_days"], 1)

    def test_splits_activity_across_midnight_and_clips_to_requested_range(self):
        activity = self.activity(
            ["2026-07-16T23:55:00Z"], start="2026-07-16", end="2026-07-17"
        )

        self.assertEqual(activity["total_seconds"], 10 * 60)
        self.assertEqual([row["active_seconds"] for row in activity["days"]], [5 * 60, 5 * 60])
        self.assertEqual(activity["active_days"], 2)

    def test_request_before_range_can_carry_activity_into_first_day(self):
        activity = self.activity(["2026-07-15T23:55:00Z"])

        self.assertEqual(activity["total_seconds"], 5 * 60)
        self.assertEqual(activity["request_count"], 0)
        self.assertEqual(activity["focus_blocks"], 1)


if __name__ == "__main__":
    unittest.main()
