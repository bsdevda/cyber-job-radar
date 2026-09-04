from __future__ import annotations

import unittest

from src.reporting import build_report_payload, render_markdown, select_report_jobs


class ReportingTests(unittest.TestCase):
    def test_markdown_displays_fifty_active_ranked_jobs(self) -> None:
        jobs = [_job(index) for index in range(1, 61)]
        config = {
            "report_limit": 50,
            "include_seen_fallback": True,
            "strong_match_score": 80,
            "markdown_job_limit": 50,
            "markdown_apply_first_limit": 10,
            "markdown_top_match_score": 75,
            "markdown_review_limit": 50,
            "repository_url": "https://github.com/example/radar",
            "scoring_version": 2.1,
        }
        selected = select_report_jobs(jobs, config)
        self.assertEqual(len(selected), 50)
        payload = build_report_payload(
            selected,
            jobs,
            {"fixture": {"status": "ok", "jobs": 60, "errors": []}},
            collected_count=60,
            security_candidate_count=60,
            duplicate_count=0,
            rejected_count=0,
            generated_at="2026-08-17T08:00:00Z",
            config=config,
        )
        markdown = render_markdown(payload, config)
        self.assertIn("Displayed **50** ranked active jobs", markdown)
        self.assertIn("### 50.", markdown)
        self.assertNotIn("### 51.", markdown)
        self.assertIn("Update Application Tracker form", markdown)
        self.assertIn("**Job key:** `job-050`", markdown)

    def test_policy_excluded_stored_jobs_never_return_to_latest_report(self) -> None:
        eligible = _job(1)
        excluded = _job(2)
        excluded["score"] = 99
        excluded["policy_excluded"] = True
        excluded["policy_exclusion_reasons"] = ["On-site role is not located in Berlin"]
        selected = select_report_jobs(
            [excluded, eligible],
            {"report_limit": 50, "include_seen_fallback": True},
        )
        self.assertEqual([job["job_key"] for job in selected], [eligible["job_key"]])


def _job(index: int) -> dict:
    return {
        "job_key": f"job-{index:03d}",
        "status": "SEEN_BEFORE",
        "application_status": "NEW",
        "score": 70,
        "raw_score": 70,
        "score_label": "GOOD",
        "title": f"Security Engineer {index}",
        "company": f"Company {index}",
        "location": "Berlin, Germany",
        "location_analysis": {
            "eligible": True,
            "reason": "Germany/Berlin eligibility detected",
        },
        "remote": False,
        "hybrid": True,
        "role_family": {"label": "Security Engineering"},
        "seniority_analysis": {"label": "Mid-level or unspecified"},
        "source": "Fixture",
        "sources": ["Fixture"],
        "ats": "",
        "priority_employer": False,
        "published_at": "2026-08-16T08:00:00Z",
        "first_seen": "2026-08-16T08:00:00Z",
        "url": f"https://example.test/jobs/{index}",
        "apply_url": f"https://example.test/jobs/{index}",
        "canonical_url": f"https://example.test/jobs/{index}",
        "description": "Security engineering role using OWASP and Python.",
        "skill_matches": {"match": ["owasp", "python"], "partial": []},
        "mandatory_gaps": [],
        "potential_gaps": [],
        "optional_gaps": [],
        "match_reasons": ["Relevant security role."],
        "warnings": [],
        "german_requirement": "No German requirement detected",
    }


if __name__ == "__main__":
    unittest.main()
