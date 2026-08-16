from __future__ import annotations

import unittest

from src.analysis import (
    analyze_posting_age,
    analyze_skill_requirements,
    detect_german_requirement,
    extract_experience,
)


class AnalysisTests(unittest.TestCase):
    def test_detects_german_nice_to_have(self) -> None:
        result = detect_german_requirement("English is required. German B1 would be nice to have.")
        self.assertEqual(result["category"], "nice")
        self.assertFalse(result["mandatory"])

    def test_detects_mandatory_b2(self) -> None:
        result = detect_german_requirement("German B2 is required for client workshops.")
        self.assertEqual(result["category"], "B2")
        self.assertTrue(result["mandatory"])

    def test_detects_advanced_german_without_cefr_level(self) -> None:
        for text in (
            "Du verfügst über sehr gute Deutschkenntnisse in Wort und Schrift.",
            "Fluency in German and English; other European languages are a bonus.",
        ):
            with self.subTest(text=text):
                result = detect_german_requirement(text)
                self.assertEqual(result["category"], "advanced")
                self.assertTrue(result["mandatory"])

    def test_does_not_treat_german_company_name_as_language_requirement(self) -> None:
        result = detect_german_requirement(
            "Trusted by Bosch and Deutsche Telekom, we build security software in an English-speaking team."
        )
        self.assertEqual(result["category"], "none")
        self.assertFalse(result["mandatory"])

    def test_extracts_experience_not_unrelated_numbers(self) -> None:
        result = extract_experience("We have 500 employees. You need at least 3 years of security experience.")
        self.assertIsNotNone(result)
        self.assertEqual(result["min_years"], 3)

    def test_returns_none_without_experience_context(self) -> None:
        self.assertIsNone(extract_experience("Annual learning budget of 2,000 EUR and 30 vacation days."))

    def test_posting_age_is_deterministic(self) -> None:
        result = analyze_posting_age(
            "2026-04-01T00:00:00Z", "2026-08-15T00:00:00Z"
        )
        self.assertEqual(result["age_days"], 136)
        self.assertEqual(result["category"], "older")

    def test_nice_to_have_section_propagates_to_following_skills(self) -> None:
        requirements = analyze_skill_requirements(
            "WHAT YOU WILL NEED\nPractical knowledge of Kubernetes.\n"
            "NICE-TO-HAVE\nFamiliarity with Terraform.\nWHAT WE OFFER\nTraining budget.",
            {"kubernetes": ["kubernetes"], "terraform": ["terraform"]},
            {"kubernetes": "missing", "terraform": "missing"},
        )
        by_skill = {item["skill"]: item for item in requirements}
        self.assertEqual(by_skill["kubernetes"]["requirement"], "mandatory")
        self.assertEqual(by_skill["terraform"]["requirement"], "optional")


if __name__ == "__main__":
    unittest.main()
