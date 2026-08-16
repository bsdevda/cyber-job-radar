from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.application_tracker import (
    ApplicationDataError,
    normalize_applications,
    set_application,
    write_application_csv,
)


class ApplicationTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = [
            {
                "job_key": "job-1",
                "company": "SecureCo",
                "title": "Application Security Engineer",
                "score": 86,
                "apply_url": "https://example.test/apply",
            }
        ]

    def test_set_enriches_record_and_defaults_application_date(self) -> None:
        applications = set_application(
            {},
            self.jobs,
            "job-1",
            {"status": "APPLIED", "cv_version": "appsec-v5", "notes": "Employer site"},
            "2026-08-16T12:00:00Z",
        )
        record = applications["job-1"]
        self.assertEqual(record["company"], "SecureCo")
        self.assertEqual(record["position"], "Application Security Engineer")
        self.assertEqual(record["application_date"], "2026-08-16")
        self.assertEqual(record["radar_recommendation"], "APPLY FIRST")
        self.assertEqual(record["radar_score"], 86)

    def test_rejects_bad_date_status_and_incomplete_manual_record(self) -> None:
        invalid = [
            {"x": {"company": "Co", "position": "Role", "status": "MAYBE"}},
            {
                "x": {
                    "company": "Co",
                    "position": "Role",
                    "status": "APPLIED",
                    "application_date": "16-08-2026",
                }
            },
            {"x": {"status": "REVIEW"}},
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ApplicationDataError):
                normalize_applications(payload, [], "2026-08-16T12:00:00Z")

    def test_csv_contains_required_application_fields(self) -> None:
        applications = set_application(
            {}, self.jobs, "job-1", {"status": "REVIEW"}, "2026-08-16T12:00:00Z"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "applications.csv"
            write_application_csv(path, applications)
            contents = path.read_text(encoding="utf-8")
        self.assertIn("company,position,application_date,radar_recommendation", contents)
        self.assertIn("SecureCo,Application Security Engineer", contents)


if __name__ == "__main__":
    unittest.main()
