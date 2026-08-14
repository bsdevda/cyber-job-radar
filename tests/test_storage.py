from __future__ import annotations

import unittest

from src.storage import apply_seen_tracking


class StorageTests(unittest.TestCase):
    def test_marks_new_then_seen_then_updated(self) -> None:
        seen = {}
        job = {"job_key": "abc", "content_hash": "one", "company": "Secure", "title": "Security Engineer", "url": "https://example.com"}
        seen, _ = apply_seen_tracking([job], seen, "2026-08-01T07:00:00Z", 30)
        self.assertEqual(job["status"], "NEW")

        unchanged = dict(job)
        seen, _ = apply_seen_tracking([unchanged], seen, "2026-08-02T07:00:00Z", 30)
        self.assertEqual(unchanged["status"], "SEEN_BEFORE")

        changed = dict(job, content_hash="two")
        seen, events = apply_seen_tracking([changed], seen, "2026-08-03T07:00:00Z", 30)
        self.assertEqual(changed["status"], "UPDATED")
        self.assertEqual(events[0]["event"], "UPDATED")

    def test_does_not_expire_jobs_when_all_sources_failed(self) -> None:
        seen = {
            "abc": {
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "content_hash": "one",
                "status": "SEEN_BEFORE",
            }
        }
        seen, events = apply_seen_tracking([], seen, "2026-08-14T07:00:00Z", 30, allow_expiry=False)
        self.assertEqual(seen["abc"]["status"], "SEEN_BEFORE")
        self.assertEqual(events, [])

    def test_expires_stale_job_after_window(self) -> None:
        seen = {
            "abc": {
                "first_seen": "2026-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "content_hash": "one",
                "status": "SEEN_BEFORE",
            }
        }
        seen, events = apply_seen_tracking([], seen, "2026-08-14T07:00:00Z", 30, allow_expiry=True)
        self.assertEqual(seen["abc"]["status"], "REMOVED")
        self.assertEqual(events[0]["event"], "REMOVED")


if __name__ == "__main__":
    unittest.main()
