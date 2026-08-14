from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.analysis import detect_german_requirement, detect_skills, extract_experience
from src.filters import hard_filter
from src.normalize import normalize_job
from src.scoring import SCORE_WEIGHTS, score_job


ROOT = Path(__file__).resolve().parents[1]


class FiltersAndScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads((ROOT / "config/search_config.json").read_text(encoding="utf-8"))
        cls.profile = json.loads((ROOT / "config/candidate_profile.json").read_text(encoding="utf-8"))

    def _job(self, title: str, description: str, location: str = "Berlin") -> dict:
        job = normalize_job(
            {
                "source": "Test",
                "source_id": "1",
                "company": "Secure",
                "title": title,
                "location": location,
                "remote": False,
                "url": "https://example.com/1",
                "published_at": "2026-08-14T00:00:00Z",
                "description": description,
                "salary": "",
                "employment_type": "Full-Time",
                "tags": [],
            }
        )
        job["german_analysis"] = detect_german_requirement(job["description"])
        job["experience_analysis"] = extract_experience(job["description"])
        skills, matches = detect_skills(job["description"], self.config["skill_aliases"], self.profile["skill_status"])
        job["skills_detected"] = skills
        job["skill_matches"] = matches
        return job

    def test_rejects_principal_role(self) -> None:
        job = self._job("Principal Security Engineer", "Lead application security and OWASP work.")
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("seniority" in reason for reason in reasons))

    def test_rejects_native_german_requirement(self) -> None:
        job = self._job("Security Consultant", "Native German is mandatory. Perform penetration testing and OWASP reviews.")
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("Native German" in reason for reason in reasons))

    def test_score_is_transparent_and_bounded(self) -> None:
        job = self._job(
            "Application Security Engineer",
            "Perform API security, web security, OWASP, Burp Suite, SAST, DAST, threat modeling and secure SDLC reviews. "
            "A computer science degree and 3+ years of security experience are required. German is beneficial.",
        )
        allowed, _ = hard_filter(job, self.config)
        self.assertTrue(allowed)
        score_job(job, self.config, self.profile)
        self.assertEqual(set(job["score_breakdown"]), set(SCORE_WEIGHTS))
        self.assertEqual(job["score"], sum(job["score_breakdown"].values()))
        self.assertGreaterEqual(job["score"], 70)
        self.assertLessEqual(job["score"], 100)


if __name__ == "__main__":
    unittest.main()
