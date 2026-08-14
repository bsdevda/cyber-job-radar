from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def apply_seen_tracking(
    jobs: list[dict[str, Any]],
    seen: dict[str, dict[str, Any]],
    now: str,
    expire_after_days: int,
    allow_expiry: bool = True,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    observed: set[str] = set()
    for job in jobs:
        key = job["job_key"]
        observed.add(key)
        previous = seen.get(key)
        if previous is None:
            status = "NEW"
            first_seen = now
            events.append(_event(now, key, "NEW", job))
        else:
            first_seen = previous.get("first_seen", now)
            status = (
                "UPDATED"
                if previous.get("status") == "REMOVED" or previous.get("content_hash") != job.get("content_hash")
                else "SEEN_BEFORE"
            )
            if status == "UPDATED":
                events.append(_event(now, key, "UPDATED", job))
        job["first_seen"] = first_seen
        job["last_seen"] = now
        job["status"] = status
        seen[key] = {
            "first_seen": first_seen,
            "last_seen": now,
            "content_hash": job.get("content_hash", ""),
            "status": status,
            "company": job.get("company", ""),
            "title": job.get("title", ""),
            "url": job.get("url", ""),
        }

    if not allow_expiry:
        return seen, events
    cutoff = _parse_datetime(now) - timedelta(days=expire_after_days)
    for key, record in seen.items():
        if key in observed or record.get("status") == "REMOVED":
            continue
        last_seen = _parse_datetime(record.get("last_seen", now))
        if last_seen < cutoff:
            record["status"] = "REMOVED"
            events.append(
                {
                    "at": now,
                    "job_key": key,
                    "event": "REMOVED",
                    "company": record.get("company", ""),
                    "title": record.get("title", ""),
                }
            )
    return seen, events


def merge_job_database(
    previous_jobs: list[dict[str, Any]],
    current_jobs: list[dict[str, Any]],
    seen: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key = {job["job_key"]: job for job in previous_jobs if job.get("job_key")}
    for job in current_jobs:
        by_key[job["job_key"]] = job
    current_keys = {current["job_key"] for current in current_jobs}
    for key, job in by_key.items():
        if key in seen and key not in current_keys:
            job["status"] = seen[key].get("status", job.get("status", "SEEN_BEFORE"))
            job["last_seen"] = seen[key].get("last_seen", job.get("last_seen", ""))
    return sorted(by_key.values(), key=lambda job: (job.get("status") == "REMOVED", -int(job.get("score", 0)), job.get("company", "")))


def append_run_history(
    history: dict[str, Any],
    run_summary: dict[str, Any],
    events: list[dict[str, Any]],
    limit: int,
) -> dict[str, Any]:
    runs = list(history.get("runs", []))
    stored_events = list(history.get("events", []))
    runs.append(run_summary)
    stored_events.extend(events)
    history["runs"] = runs[-limit:]
    history["events"] = stored_events[-limit * 50 :]
    return history


def _event(at: str, key: str, event: str, job: dict[str, Any]) -> dict[str, Any]:
    return {
        "at": at,
        "job_key": key,
        "event": event,
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "score": job.get("score", 0),
    }


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, AttributeError):
        return datetime.now(UTC)
