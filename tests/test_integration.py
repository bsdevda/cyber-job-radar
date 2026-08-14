from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.main import main, run


ROOT = Path(__file__).resolve().parents[1]


def prepare_isolated_project(target: Path) -> None:
    """Create a test project that never inherits mutable production job data."""
    shutil.copytree(ROOT / "config", target / "config")
    # The real watchlist is intentionally user-editable. Integration expectations
    # must not change when the user adds their own Greenhouse employers.
    (target / "config/companies.json").write_text(
        json.dumps(
            {
                "priority_companies": [],
                "greenhouse": [],
                "lever": [],
                "ashby": [],
                "recruitee": [],
                "smartrecruiters": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (target / "data").mkdir(parents=True)
    (target / "reports/archive").mkdir(parents=True)
    clean_data = {
        "jobs.json": [],
        "seen_jobs.json": {},
        "applications.json": {},
        "job_history.json": {"runs": [], "events": []},
    }
    for filename, payload in clean_data.items():
        (target / "data" / filename).write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8"
        )


class IntegrationTests(unittest.TestCase):
    def test_offline_end_to_end_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            target = Path(temp_directory)
            prepare_isolated_project(target)
            payload = run(target, ROOT / "tests/fixtures", no_archive=False)
            self.assertEqual(payload["summary"]["jobs_collected"], 5)
            self.assertEqual(payload["summary"]["relevant_jobs_in_current_run"], 2)
            self.assertEqual(payload["summary"]["new_jobs"], 2)
            self.assertTrue((target / "reports/latest.md").exists())
            self.assertTrue((target / "data/source_health.json").exists())
            self.assertEqual(payload["source_status"]["greenhouse"]["status"], "idle")
            jobs = json.loads((target / "data/jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(len(jobs), 2)
            self.assertTrue(all(job["description"] for job in jobs))

    def test_offline_run_with_configured_greenhouse_board(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            target = Path(temp_directory)
            prepare_isolated_project(target)
            companies_path = target / "config/companies.json"
            companies = json.loads(companies_path.read_text(encoding="utf-8"))
            companies["greenhouse"] = [
                {
                    "name": "SecureCo GmbH",
                    "board": "secureco",
                    "priority": True,
                    "enabled": True,
                }
            ]
            companies_path.write_text(
                json.dumps(companies, indent=2) + "\n", encoding="utf-8"
            )

            payload = run(target, ROOT / "tests/fixtures", no_archive=True)
            self.assertEqual(payload["summary"]["jobs_collected"], 6)
            self.assertEqual(payload["source_status"]["greenhouse"]["status"], "ok")
            self.assertEqual(payload["source_status"]["greenhouse"]["jobs"], 1)
            jobs = json.loads((target / "data/jobs.json").read_text(encoding="utf-8"))
            greenhouse_jobs = [job for job in jobs if job.get("ats") == "greenhouse"]
            self.assertEqual(len(greenhouse_jobs), 1)
            self.assertTrue(greenhouse_jobs[0]["priority_employer"])
            report = (target / "reports/latest.md").read_text(encoding="utf-8")
            self.assertIn("**ATS:** Greenhouse", report)
            self.assertIn("**Priority employer:** YES", report)

    def test_one_source_failure_does_not_stop_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            target = Path(temp_directory) / "project"
            fixtures = Path(temp_directory) / "fixtures"
            prepare_isolated_project(target)
            fixtures.mkdir()
            shutil.copy(ROOT / "tests/fixtures/arbeitnow.json", fixtures / "arbeitnow.json")
            payload = run(target, fixtures, no_archive=True)
            self.assertTrue(payload["source_status"]["arbeitnow"]["ok"])
            self.assertFalse(payload["source_status"]["remotive"]["ok"])
            self.assertEqual(payload["source_status"]["greenhouse"]["status"], "idle")
            self.assertEqual(payload["summary"]["relevant_jobs_in_current_run"], 1)
            self.assertTrue((target / "reports/latest.md").exists())

    def test_all_source_failure_is_reported_as_a_real_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_directory:
            target = Path(temp_directory) / "project"
            fixtures = Path(temp_directory) / "empty-fixtures"
            prepare_isolated_project(target)
            fixtures.mkdir()
            payload = run(target, fixtures, no_archive=True)
            self.assertTrue(payload["all_sources_failed"])
            self.assertEqual(payload["source_status"]["arbeitnow"]["status"], "failed")
            self.assertEqual(payload["source_status"]["remotive"]["status"], "failed")
            self.assertEqual(payload["source_status"]["greenhouse"]["status"], "idle")
            self.assertTrue((target / "data/source_health.json").exists())
            self.assertEqual(
                main(
                    [
                        "--project-root",
                        str(target),
                        "--fixture-dir",
                        str(fixtures),
                        "--no-archive",
                    ]
                ),
                2,
            )


if __name__ == "__main__":
    unittest.main()
