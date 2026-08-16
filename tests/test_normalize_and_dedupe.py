from __future__ import annotations

import unittest

from src.deduplication import deduplicate_jobs
from src.normalize import job_key_for, normalize_job


class NormalizationAndDeduplicationTests(unittest.TestCase):
    def _raw(self, source: str, url: str, location: str = "Berlin, Deutschland") -> dict:
        return {
            "source": source,
            "source_id": source,
            "company": "Secure GmbH",
            "title": "Application Security Engineer (m/f/d)",
            "location": location,
            "remote": False,
            "url": url,
            "published_at": "2026-08-14T06:00:00Z",
            "description": "<p>OWASP and API security</p>",
            "salary": "",
            "employment_type": "Full-Time",
            "tags": [],
        }

    def test_normalizes_berlin_and_html(self) -> None:
        job = normalize_job(self._raw("One", "https://example.com/job?utm_source=x"))
        self.assertEqual(job["location"], "Berlin, Germany")
        self.assertEqual(job["country"], "Germany")
        self.assertEqual(job["description"], "OWASP and API security")
        self.assertEqual(job["url"], "https://example.com/job")

    def test_job_key_is_stable_for_title_gender_suffix(self) -> None:
        left = job_key_for("Secure GmbH", "Application Security Engineer (m/f/d)", "Berlin, Germany")
        right = job_key_for("Secure GmbH", "Application Security Engineer", "Berlin, Germany")
        self.assertEqual(left, right)

    def test_deduplicates_across_sources(self) -> None:
        left = normalize_job(self._raw("Arbeitnow", "https://arbeitnow.com/jobs/1"))
        greenhouse = self._raw("Greenhouse", "https://boards.greenhouse.io/secure/jobs/1")
        greenhouse["ats"] = "greenhouse"
        greenhouse["apply_url"] = greenhouse["url"]
        right = normalize_job(greenhouse)
        result = deduplicate_jobs([left, right])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["sources"], ["Arbeitnow", "Greenhouse"])
        self.assertEqual(result[0]["url"], "https://boards.greenhouse.io/secure/jobs/1")
        self.assertEqual(result[0]["ats"], "greenhouse")
        self.assertEqual(result[0]["source"], "Greenhouse")

    def test_deduplicates_identical_company_description_across_titles_and_locations(self) -> None:
        description = " ".join(
            [
                "Implement security hardening for Linux and Windows systems, Active Directory, firewalls, audits, and customer projects."
            ]
            * 8
        )
        hamburg_raw = self._raw("Personio", "https://secure.jobs.personio.de/job/1", "Hamburg")
        hamburg_raw["company"] = "Scalian Germany AG"
        hamburg_raw["title"] = "IT Cyber Consultant - IT Security and Hardening"
        hamburg_raw["description"] = description
        berlin_raw = self._raw("Personio", "https://secure.jobs.personio.de/job/2", "Berlin")
        berlin_raw["company"] = "Scalian Germany AG"
        berlin_raw["title"] = "Network Security Cisco Bash - Cyber Security Engineer"
        berlin_raw["description"] = description + " Employee benefit: Blinkist."

        result = deduplicate_jobs(
            [normalize_job(hamburg_raw), normalize_job(berlin_raw)],
            {"duplicate_description_min_chars": 500},
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["location"], "Berlin, Germany")
        self.assertEqual(result[0]["url"], "https://secure.jobs.personio.de/job/2")


if __name__ == "__main__":
    unittest.main()
