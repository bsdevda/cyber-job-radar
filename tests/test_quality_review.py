from __future__ import annotations

import unittest

from src.quality_review import (
    QualityFeedbackError,
    build_quality_review,
    empty_feedback,
    record_job_review,
    record_missed_job,
    render_quality_review_markdown,
)


class QualityReviewTests(unittest.TestCase):
    def test_builds_complete_fourteen_run_review(self) -> None:
        runs = []
        for day in range(4, 18):
            runs.append(
                {
                    "generated_at": f"2026-08-{day:02d}T07:30:00Z",
                    "employer_mode": "daily",
                    "quality_review_schema_version": 1,
                    "jobs_collected": 100,
                    "security_title_candidates": 10,
                    "duplicates_removed": 2,
                    "relevant_jobs_in_current_run": 4,
                    "new_jobs": 1,
                    "workflow_duration_seconds": 600,
                    "source_status": {
                        "arbeitnow": {"status": "ok"},
                        "remotive": {"status": "failed" if day == 4 else "ok"},
                        "greenhouse": {"status": "idle"},
                    },
                }
            )
        feedback = {
            "schema_version": 1,
            "job_reviews": {
                "false": {
                    "verdict": "FALSE_POSITIVE",
                    "company": "WrongCo",
                    "position": "Security Guard",
                    "score": 82,
                    "first_seen": "2026-08-05T07:30:00Z",
                    "reviewed_at": "2026-08-05T12:00:00Z",
                    "notes": "Physical security",
                },
                "good": {
                    "verdict": "SUITABLE",
                    "company": "SecureCo",
                    "position": "Application Security Engineer",
                    "score": 86,
                    "first_seen": "2026-08-06T07:30:00Z",
                    "reviewed_at": "2026-08-06T12:00:00Z",
                    "notes": "Profile fit",
                },
            },
            "missed_jobs": {
                "missed": {
                    "company": "MissedCo",
                    "position": "Penetration Tester",
                    "url": "https://example.com/missed",
                    "found_date": "2026-08-10",
                    "reason": "Unsupported source",
                }
            },
        }
        jobs = [
            {
                "job_key": "good",
                "score_breakdown": {"role_alignment": 20, "skills": 22},
            },
            {
                "job_key": "negative",
                "score_breakdown": {"role_alignment": 16, "skills": 17},
            },
        ]
        applications = {
            "good": {
                "job_key": "good",
                "application_date": "2026-08-07",
                "interview_date": "2026-08-12",
                "status": "INTERVIEW",
                "radar_score": 86,
            },
            "negative": {
                "job_key": "negative",
                "application_date": "2026-08-08",
                "rejection_date": "2026-08-11",
                "status": "REJECTED",
                "radar_score": 75,
            },
        }
        review = build_quality_review(
            {"runs": runs, "events": []},
            feedback,
            applications,
            jobs,
            "2026-08-17T08:00:00Z",
            {
                "window_runs": 14,
                "minimum_runs_before_tuning": 14,
                "minimum_reviewed_jobs_for_false_positive_rate": 2,
                "minimum_outcomes_for_score_tuning": 2,
            },
        )
        self.assertTrue(review["window"]["ready_for_tuning"])
        self.assertEqual(review["metrics"]["new_relevant_jobs_found"], 14)
        self.assertEqual(review["metrics"]["false_positives"], 1)
        self.assertEqual(review["metrics"]["missed_suitable_jobs"], 1)
        self.assertEqual(review["metrics"]["duplicates_removed"], 28)
        self.assertEqual(review["metrics"]["source_failures"], 1)
        self.assertEqual(review["metrics"]["average_workflow_duration_seconds"], 600)
        self.assertEqual(review["metrics"]["applications_submitted"], 2)
        self.assertEqual(review["metrics"]["interviews_received"], 1)
        self.assertTrue(review["score_calibration"]["ready"])
        self.assertIn("READY FOR EVIDENCE REVIEW", render_quality_review_markdown(review))

    def test_feedback_commands_validate_job_and_missed_url(self) -> None:
        jobs = [
            {
                "job_key": "known",
                "company": "SecureCo",
                "title": "Security Tester",
                "score": 81,
                "first_seen": "2026-08-17T07:30:00Z",
            }
        ]
        feedback = record_job_review(
            empty_feedback(),
            jobs,
            "known",
            "false-positive",
            "Wrong location evidence",
            "2026-08-17T12:00:00Z",
        )
        self.assertEqual(feedback["job_reviews"]["known"]["verdict"], "FALSE_POSITIVE")
        feedback = record_missed_job(
            feedback,
            "MissedCo",
            "Penetration Tester",
            "https://example.com/job",
            "2026-08-17",
            "Source not covered",
            "",
            "2026-08-17T12:00:00Z",
        )
        self.assertEqual(len(feedback["missed_jobs"]), 1)
        with self.assertRaises(QualityFeedbackError):
            record_job_review(
                feedback,
                jobs,
                "unknown",
                "suitable",
                "",
                "2026-08-17T12:00:00Z",
            )
        with self.assertRaises(QualityFeedbackError):
            record_missed_job(
                feedback,
                "MissedCo",
                "Penetration Tester",
                "not-a-url",
                "2026-08-17",
                "",
                "",
                "2026-08-17T12:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
