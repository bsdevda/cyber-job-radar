from __future__ import annotations

import unittest

from src.analysis import detect_german_requirement, extract_experience


class AnalysisTests(unittest.TestCase):
    def test_detects_german_nice_to_have(self) -> None:
        result = detect_german_requirement("English is required. German B1 would be nice to have.")
        self.assertEqual(result["category"], "nice")
        self.assertFalse(result["mandatory"])

    def test_detects_mandatory_b2(self) -> None:
        result = detect_german_requirement("German B2 is required for client workshops.")
        self.assertEqual(result["category"], "B2")
        self.assertTrue(result["mandatory"])

    def test_extracts_experience_not_unrelated_numbers(self) -> None:
        result = extract_experience("We have 500 employees. You need at least 3 years of security experience.")
        self.assertIsNotNone(result)
        self.assertEqual(result["min_years"], 3)

    def test_returns_none_without_experience_context(self) -> None:
        self.assertIsNone(extract_experience("Annual learning budget of 2,000 EUR and 30 vacation days."))


if __name__ == "__main__":
    unittest.main()
