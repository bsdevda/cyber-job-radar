from __future__ import annotations

import unittest

from src.config_validation import ConfigurationError, priority_company_names, validate_companies_config


class CompanyConfigurationTests(unittest.TestCase):
    def test_valid_greenhouse_config_and_priority(self) -> None:
        config = {
            "priority_companies": ["Legacy GmbH"],
            "greenhouse": [
                {
                    "name": "SecureCo GmbH",
                    "board": "secureco",
                    "enabled": True,
                    "priority": True,
                }
            ],
            "lever": [],
            "ashby": [],
            "recruitee": [],
            "smartrecruiters": [],
        }
        self.assertIs(validate_companies_config(config), config)
        self.assertEqual(priority_company_names(config), {"legacy gmbh", "secureco gmbh"})

    def test_rejects_missing_identifier_invalid_boolean_and_unknown_ats(self) -> None:
        invalid_configs = [
            {"greenhouse": [{"name": "No Board"}]},
            {"greenhouse": [{"name": "Co", "board": "co", "enabled": "yes"}]},
            {"unknown_ats": []},
            {"greenhouse": "not a list"},
        ]
        for config in invalid_configs:
            with self.subTest(config=config), self.assertRaises(ConfigurationError):
                validate_companies_config(config)

    def test_rejects_duplicate_company_or_identifier(self) -> None:
        for duplicate in (
            [
                {"name": "SecureCo", "board": "secureco"},
                {"name": "Other", "board": "SECURECO"},
            ],
            [
                {"name": "SecureCo GmbH", "board": "secureco"},
                {"name": "SecureCo GmbH", "board": "secureco-2"},
            ],
        ):
            with self.subTest(duplicate=duplicate), self.assertRaises(ConfigurationError):
                validate_companies_config({"greenhouse": duplicate})

    def test_validates_startup_hiring_metadata(self) -> None:
        valid = {
            "ashby": [
                {
                    "name": "Berlin Secure",
                    "board": "berlin-secure",
                    "category": "berlin_cybersecurity_startup",
                    "current_security_hiring": True,
                    "security_hiring_verified_at": "2026-08-16",
                    "security_roles_verified": ["Security Engineer"],
                }
            ]
        }
        self.assertIs(validate_companies_config(valid), valid)
        invalid_values = [
            {**valid["ashby"][0], "current_security_hiring": "yes"},
            {**valid["ashby"][0], "security_hiring_verified_at": "16-08-2026"},
            {**valid["ashby"][0], "security_roles_verified": [""]},
        ]
        for entry in invalid_values:
            with self.subTest(entry=entry), self.assertRaises(ConfigurationError):
                validate_companies_config({"ashby": [entry]})


if __name__ == "__main__":
    unittest.main()
