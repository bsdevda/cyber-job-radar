from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.analysis import (
    analyze_posting_age,
    analyze_skill_requirements,
    detect_german_requirement,
    detect_skills,
    extract_experience,
)
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
        requirements = analyze_skill_requirements(
            job["description"], self.config["skill_aliases"], self.profile["skill_status"]
        )
        job["skill_requirements"] = requirements
        job["mandatory_gaps"] = [
            item
            for item in requirements
            if item["requirement"] == "mandatory"
            and item["profile_status"] in {"partial", "missing"}
        ]
        return job

    def test_rejects_principal_role(self) -> None:
        job = self._job("Principal Security Engineer", "Lead application security and OWASP work.")
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("seniority" in reason for reason in reasons))

    def test_rejects_staff_plus_and_remote_canada(self) -> None:
        staff = self._job(
            "Staff+ Application Security Engineer",
            "Lead application security and OWASP work.",
        )
        allowed, reasons = hard_filter(staff, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("Staff/Principal" in reason for reason in reasons))

        canada = self._job(
            "Product Security Engineer",
            "Perform product security reviews.",
            location="Remote Canada",
        )
        canada["remote"] = True
        allowed, reasons = hard_filter(canada, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("outside" in reason for reason in reasons))

    def test_explicit_us_location_overrides_worldwide_company_copy(self) -> None:
        job = self._job(
            "Product Security Engineer",
            "We are a global remote company and work from anywhere. Perform product security reviews.",
            location="Remote - United States",
        )
        job["remote"] = True
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("outside" in reason for reason in reasons))

        job = self._job(
            "Application Security Engineer",
            "Candidates in Germany can sometimes work with our global team.",
            location="Remote US",
        )
        job["remote"] = True
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("outside" in reason for reason in reasons))

    def test_rejects_non_cyber_title_with_security_terms_only_in_description(self) -> None:
        job = self._job(
            "Cloud Engineer",
            "Maintain cloud systems using IAM, vulnerability management, security testing, and incident response.",
        )
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertIn("Insufficient cybersecurity relevance", reasons)

        professor = self._job(
            "Professor of Cybersecurity",
            "Teach cybersecurity, penetration testing, and vulnerability management.",
        )
        allowed, reasons = hard_filter(professor, self.config)
        self.assertFalse(allowed)
        self.assertIn("Insufficient cybersecurity relevance", reasons)

    def test_rejects_mandatory_b2_german(self) -> None:
        job = self._job(
            "Security Tester",
            "German B2 is required. Perform OWASP security testing.",
        )
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("German B2" in reason for reason in reasons))

    def test_rejects_native_german_requirement(self) -> None:
        job = self._job("Security Consultant", "Native German is mandatory. Perform penetration testing and OWASP reviews.")
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("Native German" in reason for reason in reasons))

    def test_rejects_advanced_german_without_cefr_level(self) -> None:
        job = self._job(
            "Security Consultant",
            "Fluency in German and English is required for client communication. Perform penetration testing.",
        )
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("Advanced/fluent German" in reason for reason in reasons))

    def test_rejects_stale_posting(self) -> None:
        job = self._job(
            "Application Security Engineer",
            "Perform OWASP application security assessments.",
        )
        job["posting_age_analysis"] = analyze_posting_age(
            "2025-01-01T00:00:00Z", "2026-08-15T00:00:00Z"
        )
        allowed, reasons = hard_filter(job, self.config)
        self.assertFalse(allowed)
        self.assertTrue(any("Posting is too old" in reason for reason in reasons))

    def test_multiple_missing_mandatory_skills_are_capped_as_stretch(self) -> None:
        job = self._job(
            "Product Security Engineer",
            "You have practical knowledge of Kubernetes and Terraform. "
            "Perform OWASP application security testing and threat modeling.",
        )
        job["posting_age_analysis"] = analyze_posting_age(
            "2026-08-14T00:00:00Z", "2026-08-15T00:00:00Z"
        )
        allowed, _ = hard_filter(job, self.config)
        self.assertTrue(allowed)
        score_job(job, self.config, self.profile)
        self.assertEqual(job["score_cap"], 59)
        self.assertGreaterEqual(job["score"], self.config["relevant_score"])
        self.assertLess(job["score"], 60)

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
        self.assertEqual(job["raw_score"], sum(job["score_breakdown"].values()))
        self.assertLessEqual(job["score"], job["raw_score"])
        self.assertEqual(job["score_cap"], 79)
        self.assertGreaterEqual(job["score"], 70)
        self.assertLessEqual(job["score"], 100)


if __name__ == "__main__":
    unittest.main()
