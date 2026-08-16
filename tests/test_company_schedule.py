from __future__ import annotations

import unittest

from src.collectors.base import CollectionResult
from src.company_schedule import company_key, select_companies, update_company_health


class CompanyScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.companies = [
            {"name": "Priority", "board": "priority", "priority": True, "enabled": True},
            *[
                {"name": f"Company {index}", "board": f"company-{index}", "enabled": True}
                for index in range(25)
            ],
        ]
        self.options = {
            "daily_batch_count": 5,
            "failure_cooldown_hours": 24,
            "max_failure_cooldown_hours": 168,
            "invalid_identifier_cooldown_days": 30,
        }

    def test_daily_rotation_checks_priority_and_covers_all_nonpriority_in_five_weekdays(self) -> None:
        covered: set[str] = set()
        for day in range(10, 15):
            selected, summary = select_companies(
                "greenhouse",
                self.companies,
                {"employers": {}},
                f"2026-08-{day}T07:30:00Z",
                "daily",
                self.options,
            )
            identifiers = {company["board"] for company in selected}
            self.assertIn("priority", identifiers)
            covered.update(identifiers - {"priority"})
            self.assertEqual(summary["selected"] + summary["skipped_by_rotation"], 26)
        self.assertEqual(covered, {f"company-{index}" for index in range(25)})

    def test_full_mode_still_respects_active_cooldown(self) -> None:
        health = {
            "employers": {
                company_key("greenhouse", "company-1"): {
                    "next_retry_at": "2026-09-01T00:00:00Z"
                }
            }
        }
        selected, summary = select_companies(
            "greenhouse",
            self.companies,
            health,
            "2026-08-16T08:00:00Z",
            "full",
            self.options,
        )
        self.assertNotIn("company-1", {company["board"] for company in selected})
        self.assertEqual(summary["skipped_by_cooldown"], 1)

    def test_404_enters_invalid_identifier_cooldown_and_success_recovers(self) -> None:
        result = CollectionResult(
            source="greenhouse",
            company_results=[
                {
                    "source": "greenhouse",
                    "company": "Broken",
                    "identifier": "broken",
                    "status": "failed",
                    "http_status": 404,
                    "error": "not found",
                }
            ],
        )
        config = {"greenhouse": [{"name": "Broken", "board": "broken"}]}
        health = update_company_health(
            {"employers": {}}, config, [result], {}, "2026-08-16T08:00:00Z", self.options
        )
        entry = health["employers"]["greenhouse:broken"]
        self.assertEqual(entry["status"], "invalid_identifier")
        self.assertEqual(entry["next_retry_at"], "2026-09-15T08:00:00Z")

        result.company_results[0].update(
            {"status": "ok", "http_status": None, "error": "", "jobs": 2}
        )
        recovered = update_company_health(
            health, config, [result], {}, "2026-09-16T08:00:00Z", self.options
        )
        entry = recovered["employers"]["greenhouse:broken"]
        self.assertEqual(entry["status"], "ok")
        self.assertIsNone(entry["next_retry_at"])


if __name__ == "__main__":
    unittest.main()
