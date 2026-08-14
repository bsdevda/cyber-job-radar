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


if __name__ == "__main__":
    unittest.main()
