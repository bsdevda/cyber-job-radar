from __future__ import annotations

import unittest
from pathlib import Path

from src.collectors.greenhouse import GreenhouseCollector
from src.normalize import normalize_job


FIXTURES = Path(__file__).resolve().parent / "fixtures"
SOURCE_CONFIG = {
    "endpoint": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true",
    "delay_seconds": 0,
}


class StubClient:
    def __init__(self, responses: dict[str, object] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    def get_json(self, url: str):
        self.calls.append(url)
        board = url.split("/boards/", 1)[1].split("/", 1)[0]
        response = self.responses.get(board, {"jobs": []})
        if isinstance(response, Exception):
            raise response
        return response


class GreenhouseCollectorTests(unittest.TestCase):
    def _company(self, board: str = "secureco", **overrides) -> dict:
        company = {
            "name": "SecureCo GmbH",
            "board": board,
            "priority": False,
            "enabled": True,
        }
        company.update(overrides)
        return company

    def test_successful_fixture_parses_into_common_schema(self) -> None:
        result = GreenhouseCollector(SOURCE_CONFIG, StubClient(), [self._company()]).collect(FIXTURES)
        self.assertTrue(result.ok)
        self.assertEqual(result.companies_successful, 1)
        self.assertEqual(len(result.jobs), 1)

        job = normalize_job(result.jobs[0])
        self.assertEqual(job["company"], "SecureCo GmbH")
        self.assertEqual(job["title"], "Product Security Engineer (m/f/d)")
        self.assertEqual(job["location"], "Berlin, Germany")
        self.assertIn("threat modeling", job["description"])
        self.assertEqual(job["source"], "Greenhouse")
        self.assertEqual(job["ats"], "greenhouse")
        self.assertEqual(job["source_job_id"], "987654")
        self.assertEqual(job["url"], "https://boards.greenhouse.io/secureco/jobs/987654")
        self.assertEqual(job["employment_type"], "Full-time")

    def test_empty_board_is_successful(self) -> None:
        result = GreenhouseCollector(
            SOURCE_CONFIG, StubClient(), [self._company("emptyco")]
        ).collect(FIXTURES)
        self.assertTrue(result.ok)
        self.assertEqual(result.jobs, [])
        self.assertEqual(result.companies_successful, 1)

    def test_missing_fields_are_safe(self) -> None:
        client = StubClient({"minimal": {"jobs": [{}]}})
        result = GreenhouseCollector(
            SOURCE_CONFIG, client, [self._company("minimal")]
        ).collect()
        self.assertTrue(result.ok)
        job = normalize_job(result.jobs[0])
        self.assertEqual(job["company"], "SecureCo GmbH")
        self.assertEqual(job["title"], "Untitled role")
        self.assertEqual(job["source_job_id"], "")
        self.assertEqual(job["ats"], "greenhouse")

    def test_disabled_company_is_not_queried(self) -> None:
        client = StubClient()
        result = GreenhouseCollector(
            SOURCE_CONFIG, client, [self._company(enabled=False)]
        ).collect()
        self.assertTrue(result.ok)
        self.assertEqual(result.companies_checked, 0)
        self.assertEqual(client.calls, [])

    def test_one_company_failure_does_not_stop_others(self) -> None:
        client = StubClient(
            {
                "broken": RuntimeError("HTTP Error 404: board not found"),
                "secureco": {"jobs": [{"id": 1, "title": "Security Engineer"}]},
            }
        )
        result = GreenhouseCollector(
            SOURCE_CONFIG,
            client,
            [self._company("broken", name="Broken Co"), self._company()],
        ).collect()
        self.assertTrue(result.ok)
        self.assertEqual(result.companies_checked, 2)
        self.assertEqual(result.companies_successful, 1)
        self.assertEqual(result.companies_failed, 1)
        self.assertEqual(len(result.jobs), 1)
        self.assertEqual(result.errors[0]["http_status"], 404)
        self.assertEqual(result.errors[0]["company"], "Broken Co")

    def test_bad_response_or_total_http_failure_is_failed(self) -> None:
        for response in (["not", "an", "object"], RuntimeError("HTTP Error 503")):
            with self.subTest(response=response):
                result = GreenhouseCollector(
                    SOURCE_CONFIG,
                    StubClient({"broken": response}),
                    [self._company("broken")],
                ).collect()
                self.assertFalse(result.ok)
                self.assertEqual(result.companies_failed, 1)
                self.assertEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()
