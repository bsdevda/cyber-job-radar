from __future__ import annotations

import unittest
from pathlib import Path

from src.collectors.ashby import AshbyCollector
from src.collectors.lever import LeverCollector
from src.collectors.personio import PersonioCollector
from src.normalize import normalize_job


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class StubClient:
    def get_json(self, url: str):
        raise AssertionError(f"Fixture test unexpectedly called the network: {url}")

    def get_text(self, url: str, accept: str = ""):
        raise AssertionError(f"Fixture test unexpectedly called the network: {url}")


class AtsCollectorTests(unittest.TestCase):
    def test_ashby_fixture_maps_public_fields(self) -> None:
        collector = AshbyCollector(
            {"endpoint": "https://example/{board}"},
            StubClient(),
            [{"name": "SecureCo GmbH", "board": "secureco", "enabled": True}],
        )
        result = collector.collect(FIXTURES)
        self.assertTrue(result.ok)
        self.assertEqual(result.companies_successful, 1)
        job = normalize_job(result.jobs[0])
        self.assertEqual(job["ats"], "ashby")
        self.assertEqual(job["location"], "Berlin, Germany")
        self.assertTrue(job["hybrid"])
        self.assertIn("threat modelling", job["description"])

    def test_lever_fixture_maps_description_and_workplace(self) -> None:
        collector = LeverCollector(
            {"endpoint": "https://example/{site}", "eu_endpoint": "https://eu/{site}"},
            StubClient(),
            [{"name": "SecureCo GmbH", "site": "secureco", "enabled": True}],
        )
        result = collector.collect(FIXTURES)
        self.assertTrue(result.ok)
        job = normalize_job(result.jobs[0])
        self.assertEqual(job["ats"], "lever")
        self.assertEqual(job["title"], "Penetration Tester")
        self.assertTrue(job["hybrid"])
        self.assertIn("2+ years", job["description"])

    def test_personio_fixture_maps_xml_and_experience(self) -> None:
        collector = PersonioCollector(
            {"endpoint": "https://{account}.example/xml?language={language}"},
            StubClient(),
            [
                {
                    "name": "SecureCo GmbH",
                    "account": "secureco",
                    "language": "en",
                    "enabled": True,
                }
            ],
        )
        result = collector.collect(FIXTURES)
        self.assertTrue(result.ok)
        job = normalize_job(result.jobs[0])
        self.assertEqual(job["ats"], "personio")
        self.assertEqual(job["title"], "Security Tester (m/f/d)")
        self.assertIn("1-2 years of experience", job["description"])
        self.assertIn("personio.de/job/4103", job["url"])


if __name__ == "__main__":
    unittest.main()
