from __future__ import annotations

import unittest

from src.collectors.base import CollectionResult
from src.source_health import build_source_health


class SourceHealthTests(unittest.TestCase):
    def test_calculates_ok_partial_failed_and_idle(self) -> None:
        results = [
            CollectionResult(source="arbeitnow", jobs=[{"id": 1}], ok=True, requests=1),
            CollectionResult(
                source="greenhouse",
                jobs=[{"id": 2}],
                ok=True,
                companies_checked=2,
                companies_successful=1,
                companies_failed=1,
                errors=[{"message": "Greenhouse | Broken Co | HTTP 404"}],
            ),
            CollectionResult(source="remotive", ok=False, error="network timeout", requests=3),
            CollectionResult(source="greenhouse-idle", ok=True),
        ]
        # A Version 1.1 Greenhouse result with no enabled company is explicitly idle.
        results[3].source = "greenhouse"
        health = build_source_health(results, "2026-08-14T07:30:00Z")
        # Duplicate source names overwrite by design, so verify idle separately below.
        self.assertEqual(health["sources"]["arbeitnow"]["status"], "ok")
        self.assertEqual(health["sources"]["remotive"]["status"], "failed")
        self.assertFalse(health["all_sources_failed"])

        partial = build_source_health(results[:2], "2026-08-14T07:30:00Z")
        self.assertEqual(partial["sources"]["greenhouse"]["status"], "partial")
        self.assertEqual(partial["sources"]["greenhouse"]["companies_failed"], 1)

        idle = build_source_health(
            [CollectionResult(source="greenhouse")], "2026-08-14T07:30:00Z"
        )
        self.assertEqual(idle["sources"]["greenhouse"]["status"], "idle")

    def test_all_operational_sources_failed_ignores_idle_source(self) -> None:
        health = build_source_health(
            [
                CollectionResult(source="arbeitnow", ok=False, error="timeout"),
                CollectionResult(source="remotive", ok=False, error="HTTP 503"),
                CollectionResult(source="greenhouse"),
            ],
            "2026-08-14T07:30:00Z",
        )
        self.assertTrue(health["all_sources_failed"])


if __name__ == "__main__":
    unittest.main()
