from __future__ import annotations

import unittest

from src.notifications import build_job_alert, render_job_alert_markdown


class NotificationTests(unittest.TestCase):
    def test_alerts_only_for_new_strong_unapplied_jobs(self) -> None:
        jobs = [
            _job("one", "NEW", 86),
            _job("two", "NEW", 82),
            _job("three", "SEEN_BEFORE", 95),
            _job("four", "NEW", 79),
            {**_job("five", "NEW", 90), "application_status": "APPLIED"},
        ]
        config = {
            "notifications": {
                "enabled": True,
                "minimum_score": 80,
                "new_statuses": ["NEW"],
                "maximum_jobs_per_alert": 10,
            }
        }
        alert = build_job_alert(jobs, config, "2026-08-17T07:30:00Z")
        self.assertTrue(alert["has_alert"])
        self.assertEqual([item["job_key"] for item in alert["jobs"]], ["one", "two"])
        self.assertIn("[Job Radar] 2 new strong matches", alert["title"])
        markdown = render_job_alert_markdown(alert)
        self.assertIn("APPLY FIRST", markdown)
        self.assertIn("APPLY", markdown)
        self.assertIn("cyber-job-radar-alert:", markdown)

    def test_no_alert_is_an_empty_body(self) -> None:
        alert = build_job_alert(
            [_job("one", "SEEN_BEFORE", 92)],
            {"notifications": {"enabled": True, "minimum_score": 80}},
            "2026-08-17T07:30:00Z",
        )
        self.assertFalse(alert["has_alert"])
        self.assertEqual(render_job_alert_markdown(alert), "")


def _job(key: str, status: str, score: int) -> dict:
    return {
        "job_key": key,
        "status": status,
        "application_status": "NEW",
        "score": score,
        "title": "Application Security Engineer",
        "company": "SecureCo",
        "location": "Berlin",
        "published_at": "2026-08-16T00:00:00Z",
        "url": "https://example.com/job",
        "role_family": {"label": "Application Security"},
        "match_reasons": ["Relevant role family."],
        "warnings": [],
    }


if __name__ == "__main__":
    unittest.main()
