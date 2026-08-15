from __future__ import annotations

import unittest

from src.analytics import build_weekly_snapshot, update_weekly_analytics


class AnalyticsTests(unittest.TestCase):
    def test_builds_skill_gap_and_application_funnel(self) -> None:
        jobs = [
            {
                "status": "NEW",
                "score": 78,
                "role_family": {"label": "Application Security"},
                "mandatory_gaps": [{"skill": "kubernetes"}],
                "potential_gaps": [{"skill": "go"}],
                "optional_gaps": [],
                "skill_matches": {"partial": ["aws"]},
            }
        ]
        applications = {
            "one": {"status": "APPLIED"},
            "two": {"status": "INTERVIEW"},
            "three": {"status": "REJECTED", "response_date": "2026-08-14"},
        }
        snapshot = build_weekly_snapshot(jobs, applications, "2026-08-15T08:00:00Z")
        self.assertEqual(snapshot["week_start"], "2026-08-10")
        self.assertEqual(snapshot["skill_gaps"]["mandatory"][0]["skill"], "kubernetes")
        self.assertEqual(snapshot["application_funnel"]["applications_submitted"], 3)
        self.assertEqual(snapshot["application_funnel"]["responses_or_screens"], 2)
        self.assertEqual(snapshot["application_funnel"]["interviews"], 1)

        analytics = update_weekly_analytics({"snapshots": []}, snapshot, 52)
        updated = update_weekly_analytics(analytics, snapshot, 52)
        self.assertEqual(len(updated["snapshots"]), 1)


if __name__ == "__main__":
    unittest.main()
