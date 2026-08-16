from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import Any

from .scoring import recommendation
from .utils import iso_now, load_json, write_json_atomic


VALID_STATUSES = {
    "REVIEW",
    "SAVE",
    "APPLIED",
    "RECRUITER CONTACT",
    "PHONE SCREEN",
    "INTERVIEW",
    "TECHNICAL INTERVIEW",
    "FINAL INTERVIEW",
    "OFFER",
    "REJECTED",
    "GHOSTED",
    "WITHDRAWN",
    "SKIPPED",
}

CSV_FIELDS = [
    "job_key",
    "company",
    "position",
    "application_date",
    "radar_recommendation",
    "radar_score",
    "cv_version",
    "cover_letter_used",
    "status",
    "response_date",
    "rejection_date",
    "interview_date",
    "interview_stage",
    "final_result",
    "job_url",
    "notes",
    "updated_at",
]


class ApplicationDataError(ValueError):
    """Raised when an application record would produce misleading analytics."""


def normalize_applications(
    applications: Any,
    jobs: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(applications, dict):
        raise ApplicationDataError("data/applications.json must contain a JSON object")
    jobs_by_key = {
        str(job.get("job_key")): job for job in jobs if isinstance(job, dict) and job.get("job_key")
    }
    normalized: dict[str, dict[str, Any]] = {}
    for key in sorted(applications):
        raw = applications[key]
        if not isinstance(raw, dict):
            raise ApplicationDataError(f"Application '{key}' must be a JSON object")
        job = jobs_by_key.get(str(key), {})
        status = str(raw.get("status") or "REVIEW").strip().upper()
        if status not in VALID_STATUSES:
            raise ApplicationDataError(
                f"Application '{key}' has unsupported status '{status}'"
            )
        score = raw.get("radar_score", job.get("score"))
        try:
            score_value = int(score) if score not in {None, ""} else None
        except (TypeError, ValueError) as exc:
            raise ApplicationDataError(
                f"Application '{key}' radar_score must be an integer"
            ) from exc
        if score_value is not None and not 0 <= score_value <= 100:
            raise ApplicationDataError(
                f"Application '{key}' radar_score must be between 0 and 100"
            )
        application_date = raw.get("application_date") or raw.get("applied_date") or ""
        record = {
            "job_key": str(key),
            "company": str(raw.get("company") or job.get("company") or "").strip(),
            "position": str(raw.get("position") or job.get("title") or "").strip(),
            "application_date": str(application_date or ""),
            "radar_recommendation": str(
                raw.get("radar_recommendation")
                or (_recommendation_label(score_value) if score_value is not None else "")
            ).strip(),
            "radar_score": score_value,
            "cv_version": str(raw.get("cv_version") or "").strip(),
            "cover_letter_used": raw.get("cover_letter_used"),
            "status": status,
            "response_date": str(raw.get("response_date") or ""),
            "rejection_date": str(raw.get("rejection_date") or ""),
            "interview_date": str(raw.get("interview_date") or ""),
            "interview_stage": str(raw.get("interview_stage") or "").strip(),
            "final_result": str(raw.get("final_result") or "").strip(),
            "job_url": str(raw.get("job_url") or job.get("apply_url") or job.get("url") or "").strip(),
            "notes": str(raw.get("notes") or "").strip(),
            "updated_at": str(raw.get("updated_at") or generated_at),
        }
        if not record["company"] or not record["position"]:
            raise ApplicationDataError(
                f"Application '{key}' requires company and position (or a matching job_key)"
            )
        if record["cover_letter_used"] is not None and not isinstance(
            record["cover_letter_used"], bool
        ):
            raise ApplicationDataError(
                f"Application '{key}' cover_letter_used must be true, false, or null"
            )
        for field in (
            "application_date",
            "response_date",
            "rejection_date",
            "interview_date",
        ):
            _validate_date(record[field], key, field)
        if status in {
            "APPLIED",
            "RECRUITER CONTACT",
            "PHONE SCREEN",
            "INTERVIEW",
            "TECHNICAL INTERVIEW",
            "FINAL INTERVIEW",
            "OFFER",
            "REJECTED",
            "GHOSTED",
            "WITHDRAWN",
        } and not record["application_date"]:
            raise ApplicationDataError(
                f"Application '{key}' with status {status} requires application_date"
            )
        normalized[str(key)] = record
    return normalized


def write_application_csv(path: Path, applications: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for key in sorted(applications):
            writer.writerow(applications[key])
    temporary.replace(path)


def set_application(
    applications: dict[str, dict[str, Any]],
    jobs: list[dict[str, Any]],
    job_key: str,
    updates: dict[str, Any],
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    current = dict(applications.get(job_key, {}))
    for field, value in updates.items():
        if value is not None:
            current[field] = value
    current["updated_at"] = generated_at
    status = str(current.get("status") or "REVIEW").upper()
    if status not in {"REVIEW", "SAVE", "SKIPPED"} and not (
        current.get("application_date") or current.get("applied_date")
    ):
        current["application_date"] = generated_at[:10]
    updated = dict(applications)
    updated[job_key] = current
    return normalize_applications(updated, jobs, generated_at)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain Cyber Job Radar application records.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_parser = subparsers.add_parser("set", help="Add or update an application record")
    set_parser.add_argument("--job-key", required=True)
    set_parser.add_argument("--company")
    set_parser.add_argument("--position")
    set_parser.add_argument("--status", choices=sorted(VALID_STATUSES))
    set_parser.add_argument("--application-date")
    set_parser.add_argument("--response-date")
    set_parser.add_argument("--rejection-date")
    set_parser.add_argument("--interview-date")
    set_parser.add_argument("--interview-stage")
    set_parser.add_argument("--cv-version")
    set_parser.add_argument(
        "--cover-letter-used",
        choices=("yes", "no"),
        help="Record whether a tailored cover letter was submitted.",
    )
    set_parser.add_argument("--radar-recommendation")
    set_parser.add_argument("--radar-score", type=int)
    set_parser.add_argument("--job-url")
    set_parser.add_argument("--notes")
    set_parser.add_argument("--final-result")
    subparsers.add_parser("list", help="Print the tracked application funnel")
    subparsers.add_parser("export", help="Regenerate reports/application_tracker.csv")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.project_root.resolve()
    applications_path = root / "data/applications.json"
    csv_path = root / "reports/application_tracker.csv"
    jobs = load_json(root / "data/jobs.json", [])
    generated_at = iso_now()
    try:
        applications = normalize_applications(
            load_json(applications_path, {}), jobs, generated_at
        )
        if args.command == "set":
            updates = {
                "company": args.company,
                "position": args.position,
                "status": args.status,
                "application_date": args.application_date,
                "response_date": args.response_date,
                "rejection_date": args.rejection_date,
                "interview_date": args.interview_date,
                "interview_stage": args.interview_stage,
                "cv_version": args.cv_version,
                "cover_letter_used": (
                    args.cover_letter_used == "yes"
                    if args.cover_letter_used is not None
                    else None
                ),
                "radar_recommendation": args.radar_recommendation,
                "radar_score": args.radar_score,
                "job_url": args.job_url,
                "notes": args.notes,
                "final_result": args.final_result,
            }
            applications = set_application(
                applications, jobs, args.job_key.strip(), updates, generated_at
            )
            write_json_atomic(applications_path, applications)
            print(f"Saved application: {args.job_key.strip()}")
        write_application_csv(csv_path, applications)
        if args.command == "list":
            if not applications:
                print("No applications are tracked yet.")
            for record in applications.values():
                print(
                    f"{record['status']:<20} {record['company']} | "
                    f"{record['position']} | {record['application_date'] or '-'}"
                )
        elif args.command == "export":
            print(f"Exported {len(applications)} application(s) to {csv_path}")
        return 0
    except (ApplicationDataError, OSError) as exc:
        print(f"Application tracker error: {exc}", file=sys.stderr)
        return 1


def _recommendation_label(score: int) -> str:
    return recommendation(score).split(" - ", 1)[0]


def _validate_date(value: str, key: str, field: str) -> None:
    if not value:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ApplicationDataError(
            f"Application '{key}' field {field} must use YYYY-MM-DD"
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())
