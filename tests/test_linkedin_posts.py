from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.collectors.linkedin_posts import LinkedInPostsCollector
from src.scoring import score_job
from src.utils import HttpClient


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Authorized public post alert</title>
    <item>
      <title>We are hiring an Application Security Engineer in Berlin | LinkedIn</title>
      <link>https://www.google.com/url?url=https%3A%2F%2Fwww.linkedin.com%2Fposts%2Frecruiter_application-security-hiring-activity-123</link>
      <guid>lead-123</guid>
      <author>Secure Example GmbH</author>
      <pubDate>Sun, 16 Aug 2026 08:00:00 GMT</pubDate>
      <description>Join our English-speaking product security team. Apply now for web and API security testing.</description>
    </item>
    <item>
      <title>We are hiring an Account Executive in Berlin | LinkedIn</title>
      <link>https://www.linkedin.com/posts/recruiter_sales-hiring-activity-456</link>
      <guid>lead-456</guid>
      <description>Apply to join the sales team.</description>
    </item>
  </channel>
</rss>
"""


class LinkedInPostsCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "feeds": [],
            "feeds_env": "LINKEDIN_POST_FEEDS_JSON",
            "max_items_per_feed": 50,
            "require_linkedin_post_url": True,
        }
        self.collector = LinkedInPostsCollector(self.config, HttpClient())

    def test_parses_only_relevant_linkedin_post_leads(self) -> None:
        entries = self.collector._parse_feed(RSS)
        jobs = self.collector._map_entries(entries, "Test feed")
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["company"], "Secure Example GmbH")
        self.assertEqual(job["location"], "Berlin, Germany")
        self.assertEqual(job["lead_type"], "linkedin_post")
        self.assertEqual(
            job["url"],
            "https://www.linkedin.com/posts/recruiter_application-security-hiring-activity-123",
        )
        self.assertEqual(job["published_at"], "2026-08-16T08:00:00Z")

    def test_feed_secret_is_validated_and_deduplicated(self) -> None:
        value = json.dumps(
            [
                "https://alerts.example.test/one.xml",
                {"name": "Duplicate", "url": "https://alerts.example.test/one.xml"},
                {"name": "Disabled", "url": "https://alerts.example.test/two.xml", "enabled": False},
            ]
        )
        with patch.dict(os.environ, {"LINKEDIN_POST_FEEDS_JSON": value}):
            self.assertEqual(
                self.collector._configured_feeds(),
                [{"name": "LinkedIn post feed 1", "url": "https://alerts.example.test/one.xml"}],
            )

        with patch.dict(os.environ, {"LINKEDIN_POST_FEEDS_JSON": "not-json"}):
            with self.assertRaises(ValueError):
                self.collector._configured_feeds()

    def test_offline_fixture_never_requests_linkedin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "linkedin_posts.json"
            fixture.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "Hiring Product Security Engineer - Remote Germany",
                                "link": "https://www.linkedin.com/posts/security-recruiter_product-security-hiring-activity-999",
                                "description": "We are hiring. English-speaking security engineering vacancy.",
                                "published_at": "2026-08-16T08:00:00Z",
                                "author": "Example Security",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = self.collector.collect(Path(directory))
        self.assertTrue(result.ok)
        self.assertEqual(result.requests, 0)
        self.assertEqual(len(result.jobs), 1)

    def test_linkedin_lead_cannot_trigger_strong_match_alert(self) -> None:
        job = {
            "lead_type": "linkedin_post",
            "role_family": {"priority": 1, "label": "Application Security"},
            "skill_requirements": [],
            "skill_matches": {"match": ["owasp", "python"], "partial": [], "missing": []},
            "experience_analysis": None,
            "location_analysis": {"score": 15, "category": "eligible_germany"},
            "german_analysis": {"category": "none"},
            "seniority_analysis": {"level": "mid_unspecified"},
            "posting_age_analysis": {"age_days": 1},
            "description": "Computer science application security role",
            "mandatory_gaps": [],
            "potential_gaps": [],
            "optional_gaps": [],
        }
        score_job(job, {"stale_posting_score_cap_days": 60}, {"experience_years": 2.1})
        self.assertLessEqual(job["score"], 69)
        self.assertIn("LinkedIn post lead", " ".join(job["score_cap_reasons"]))


if __name__ == "__main__":
    unittest.main()
