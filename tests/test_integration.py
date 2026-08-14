from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.main import run


ROOT = Path(__file__).resolve().parents[1]


def prepare_isolated_project(target: Path) -> None:
    """Create a test project that never inherits mutable production job data."""
    shutil.copytree(ROOT / "config", target / "config")
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
            jobs = json.loads((target / "data/jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(len(jobs), 2)
            self.assertTrue(all(job["description"] for job in jobs))

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
            self.assertEqual(payload["summary"]["relevant_jobs_in_current_run"], 1)
            self.assertTrue((target / "reports/latest.md").exists())


if __name__ == "__main__":
    unittest.main()
