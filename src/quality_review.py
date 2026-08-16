from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .analytics import APPLICATION_STAGE
from .utils import iso_now, load_json, write_json_atomic, write_text_atomic


VALID_VERDICTS = {"SUITABLE", "FALSE_POSITIVE"}
NEGATIVE_OUTCOMES = {"REJECTED", "GHOSTED"}


class QualityFeedbackError(ValueError):
    """Raised when manual quality feedback is incomplete or misleading."""


def empty_feedback() -> dict[str, Any]:
    return {"schema_version": 1, "job_reviews": {}, "missed_jobs": {}}


def normalize_quality_feedback(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QualityFeedbackError("data/quality_feedback.json must contain a JSON object")
    job_reviews = value.get("job_reviews", {})
    missed_jobs = value.get("missed_jobs", {})
    if not isinstance(job_reviews, dict) or not isinstance(missed_jobs, dict):
        raise QualityFeedbackError("job_reviews and missed_jobs must be JSON objects")
    normalized_reviews: dict[str, dict[str, Any]] = {}
    for key, raw in job_reviews.items():
        if not isinstance(raw, dict):
            raise QualityFeedbackError(f"Job review '{key}' must be a JSON object")
        verdict = str(raw.get("verdict") or "").upper()
        if verdict not in VALID_VERDICTS:
            raise QualityFeedbackError(f"Job review '{key}' has unsupported verdict '{verdict}'")
        normalized_reviews[str(key)] = {
            "job_key": str(key),
            "verdict": verdict,
            "company": str(raw.get("company") or "").strip(),
            "position": str(raw.get("position") or "").strip(),
            "score": _optional_score(raw.get("score"), str(key)),
            "first_seen": _optional_date_or_datetime(raw.get("first_seen"), str(key), "first_seen"),
            "reviewed_at": _optional_date_or_datetime(raw.get("reviewed_at"), str(key), "reviewed_at"),
            "notes": str(raw.get("notes") or "").strip(),
        }
    normalized_missed: dict[str, dict[str, Any]] = {}
    for key, raw in missed_jobs.items():
        if not isinstance(raw, dict):
            raise QualityFeedbackError(f"Missed job '{key}' must be a JSON object")
        company = str(raw.get("company") or "").strip()
        position = str(raw.get("position") or "").strip()
        url = str(raw.get("url") or "").strip()
        found_date = str(raw.get("found_date") or "").strip()
        if not company or not position or not url or not found_date:
            raise QualityFeedbackError(
                f"Missed job '{key}' requires company, position, url, and found_date"
            )
        if not url.startswith(("https://", "http://")):
            raise QualityFeedbackError(f"Missed job '{key}' URL must start with http:// or https://")
        _validate_date(found_date, str(key), "found_date")
        normalized_missed[str(key)] = {
            "missed_key": str(key),
            "company": company,
            "position": position,
            "url": url,
            "found_date": found_date,
            "reason": str(raw.get("reason") or "").strip(),
            "notes": str(raw.get("notes") or "").strip(),
            "recorded_at": str(raw.get("recorded_at") or ""),
        }
    return {
        "schema_version": 1,
        "job_reviews": dict(sorted(normalized_reviews.items())),
        "missed_jobs": dict(sorted(normalized_missed.items())),
    }


def record_job_review(
    feedback: dict[str, Any],
    jobs: list[dict[str, Any]],
    job_key: str,
    verdict: str,
    notes: str,
    generated_at: str,
) -> dict[str, Any]:
    normalized = normalize_quality_feedback(feedback)
    job = next((item for item in jobs if str(item.get("job_key")) == job_key), None)
    if job is None:
        raise QualityFeedbackError(
            f"Unknown job_key '{job_key}'. Copy it from reports/latest.json or data/jobs.json"
        )
    verdict = verdict.upper().replace("-", "_")
    if verdict not in VALID_VERDICTS:
        raise QualityFeedbackError(f"Unsupported verdict '{verdict}'")
    normalized["job_reviews"][job_key] = {
        "job_key": job_key,
        "verdict": verdict,
        "company": str(job.get("company") or ""),
        "position": str(job.get("title") or ""),
        "score": int(job.get("score", 0)),
        "first_seen": str(job.get("first_seen") or generated_at),
        "reviewed_at": generated_at,
        "notes": notes.strip(),
    }
    return normalize_quality_feedback(normalized)


def record_missed_job(
    feedback: dict[str, Any],
    company: str,
    position: str,
    url: str,
    found_date: str,
    reason: str,
    notes: str,
    generated_at: str,
) -> dict[str, Any]:
    normalized = normalize_quality_feedback(feedback)
    company = company.strip()
    position = position.strip()
    url = url.strip()
    if not company or not position or not url:
        raise QualityFeedbackError("A missed job requires company, position, and URL")
    if not url.startswith(("https://", "http://")):
        raise QualityFeedbackError("The missed-job URL must start with http:// or https://")
    _validate_date(found_date, "new missed job", "found_date")
    key_source = "|".join((company.casefold(), position.casefold(), url.casefold()))
    key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()[:16]
    normalized["missed_jobs"][key] = {
        "missed_key": key,
        "company": company,
        "position": position,
        "url": url,
        "found_date": found_date,
        "reason": reason.strip(),
        "notes": notes.strip(),
        "recorded_at": generated_at,
    }
    return normalize_quality_feedback(normalized)


def build_quality_review(
    history: dict[str, Any],
    feedback: dict[str, Any],
    applications: dict[str, dict[str, Any]],
    jobs: list[dict[str, Any]],
    generated_at: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    feedback = normalize_quality_feedback(feedback)
    window_size = max(1, int(options.get("window_runs", 14)))
    minimum_runs = max(1, int(options.get("minimum_runs_before_tuning", window_size)))
    # Keep only the last successful record for each calendar day. Manual reruns
    # must not make a two-week baseline appear complete in one afternoon.
    daily_by_date: dict[str, dict[str, Any]] = {}
    for run in history.get("runs", []):
        if int(run.get("quality_review_schema_version", 0)) < 1:
            continue
        if str(run.get("employer_mode") or "daily") != "daily":
            continue
        run_date = str(run.get("generated_at") or "")[:10]
        if run_date:
            daily_by_date[run_date] = run
    daily_runs = [daily_by_date[key] for key in sorted(daily_by_date)][-window_size:]
    dates = [str(run.get("generated_at") or "")[:10] for run in daily_runs]
    dates = [value for value in dates if value]
    period_start = min(dates) if dates else generated_at[:10]
    period_end = max(dates) if dates else generated_at[:10]

    relevant_seen = sum(int(run.get("relevant_jobs_in_current_run", 0)) for run in daily_runs)
    new_relevant = sum(int(run.get("new_jobs", 0)) for run in daily_runs)
    collected = sum(int(run.get("jobs_collected", 0)) for run in daily_runs)
    security_candidates = sum(int(run.get("security_title_candidates", 0)) for run in daily_runs)
    duplicates = sum(int(run.get("duplicates_removed", 0)) for run in daily_runs)
    duration_values = [
        float(run["workflow_duration_seconds"])
        for run in daily_runs
        if run.get("workflow_duration_seconds") not in {None, ""}
    ]
    source_checks = source_failures = source_partials = 0
    for run in daily_runs:
        for details in run.get("source_status", {}).values():
            status = str(details.get("status") or "failed")
            if status == "idle":
                continue
            source_checks += 1
            source_failures += status == "failed"
            source_partials += status == "partial"

    job_reviews = [
        review
        for review in feedback["job_reviews"].values()
        if _in_period(review.get("first_seen") or review.get("reviewed_at"), period_start, period_end)
    ]
    false_positives = sum(review["verdict"] == "FALSE_POSITIVE" for review in job_reviews)
    suitable_reviews = sum(review["verdict"] == "SUITABLE" for review in job_reviews)
    missed_jobs = [
        missed
        for missed in feedback["missed_jobs"].values()
        if _in_period(missed.get("found_date"), period_start, period_end)
    ]

    period_applications = [
        record
        for record in applications.values()
        if _in_period(record.get("application_date"), period_start, period_end)
    ]
    period_interviews = [
        record
        for record in applications.values()
        if _interview_in_period(record, period_start, period_end)
    ]
    cohort_interviews = sum(_is_interview(record) for record in period_applications)
    score_bands = _outcomes_by_score_band(period_applications)
    calibration = _score_calibration(
        period_applications,
        jobs,
        int(options.get("minimum_outcomes_for_score_tuning", 6)),
    )
    reviewed_count = len(job_reviews)
    minimum_reviewed = max(
        1, int(options.get("minimum_reviewed_jobs_for_false_positive_rate", 5))
    )
    ready = len(daily_runs) >= minimum_runs
    metrics = {
        "relevant_job_observations": relevant_seen,
        "new_relevant_jobs_found": new_relevant,
        "reviewed_jobs": reviewed_count,
        "suitable_jobs_confirmed": suitable_reviews,
        "false_positives": false_positives,
        "false_positive_rate_percent": _rate(false_positives, reviewed_count),
        "false_positive_rate_is_reliable": reviewed_count >= minimum_reviewed,
        "missed_suitable_jobs": len(missed_jobs),
        "raw_jobs_collected": collected,
        "duplicates_removed": duplicates,
        "duplicate_rate_percent": _rate(duplicates, security_candidates),
        "source_checks": source_checks,
        "source_failures": source_failures,
        "source_partials": source_partials,
        "source_failure_rate_percent": _rate(source_failures, source_checks),
        "average_workflow_duration_seconds": round(sum(duration_values) / len(duration_values), 1)
        if duration_values
        else None,
        "workflow_duration_coverage_runs": len(duration_values),
        "applications_submitted": len(period_applications),
        "interviews_received": len(period_interviews),
        "application_cohort_interviews": cohort_interviews,
        "application_to_interview_rate_percent": _rate(
            cohort_interviews, len(period_applications)
        ),
    }
    recommendations = _recommendations(
        ready,
        metrics,
        calibration,
        minimum_reviewed,
    )
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "window": {
            "target_daily_runs": window_size,
            "completed_daily_runs": len(daily_runs),
            "minimum_runs_before_tuning": minimum_runs,
            "ready_for_tuning": ready,
            "period_start": period_start,
            "period_end": period_end,
        },
        "metrics": metrics,
        "outcomes_by_score_band": score_bands,
        "score_calibration": calibration,
        "false_positive_jobs": [
            _feedback_summary(item) for item in job_reviews if item["verdict"] == "FALSE_POSITIVE"
        ],
        "missed_jobs": list(missed_jobs),
        "recommendations": recommendations,
    }


def render_quality_review_markdown(review: dict[str, Any]) -> str:
    window = review["window"]
    metrics = review["metrics"]
    status = "READY FOR EVIDENCE REVIEW" if window["ready_for_tuning"] else "COLLECTING BASELINE"
    duration = metrics["average_workflow_duration_seconds"]
    duration_label = f"{duration:.1f} seconds" if duration is not None else "Not recorded yet"
    lines = [
        "# Cybersecurity Job Radar - 14-Run Quality Review",
        "",
        f"**Status:** {status}",
        f"**Daily runs:** {window['completed_daily_runs']}/{window['target_daily_runs']}",
        f"**Period:** {window['period_start']} to {window['period_end']}",
        f"**Generated:** {review['generated_at']}",
        "",
        "## Quality and operations",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| Relevant job observations | {metrics['relevant_job_observations']} |",
        f"| New relevant jobs found | {metrics['new_relevant_jobs_found']} |",
        f"| Manually reviewed jobs | {metrics['reviewed_jobs']} |",
        f"| False positives | {metrics['false_positives']} ({metrics['false_positive_rate_percent']}%) |",
        f"| Missed suitable jobs logged | {metrics['missed_suitable_jobs']} |",
        f"| Duplicates removed | {metrics['duplicates_removed']} ({metrics['duplicate_rate_percent']}%) |",
        f"| Source failures | {metrics['source_failures']}/{metrics['source_checks']} ({metrics['source_failure_rate_percent']}%) |",
        f"| Average workflow duration | {duration_label} |",
        f"| Applications submitted | {metrics['applications_submitted']} |",
        f"| Interviews received during period | {metrics['interviews_received']} |",
        f"| Applications from period reaching interview | {metrics['application_cohort_interviews']} ({metrics['application_to_interview_rate_percent']}%) |",
        "",
        "## Outcomes by score band",
        "",
        "| Score band | Applications | Interviews | Interview rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for band, values in review.get("outcomes_by_score_band", {}).items():
        lines.append(
            f"| {band} | {values['applications']} | {values['interviews']} | {values['interview_rate_percent']}% |"
        )
    if not review.get("outcomes_by_score_band"):
        lines.append("| No application outcomes yet | 0 | 0 | 0% |")

    lines.extend(["", "## Scoring calibration", ""])
    calibration = review.get("score_calibration", {})
    lines.append(calibration.get("message", "No calibration evidence yet."))
    component_deltas = calibration.get("component_deltas", {})
    if component_deltas:
        lines.extend(
            [
                "",
                "| Score component | Interviewed average | Negative-outcome average | Difference |",
                "| --- | ---: | ---: | ---: |",
            ]
        )
        for component, values in component_deltas.items():
            lines.append(
                f"| {component} | {values['interviewed_average']} | "
                f"{values['negative_average']} | {values['difference']:+} |"
            )

    lines.extend(["", "## Recommendations", ""])
    lines.extend(f"- {item}" for item in review.get("recommendations", []))
    lines.extend(
        [
            "",
            "## Manual feedback still required",
            "",
            "The radar cannot know a false positive or missed vacancy without your review. Record both throughout the 14-run period; otherwise those metrics are incomplete.",
            "",
            "Scoring weights are never changed automatically. Apply a recommendation only after checking the underlying vacancies and adding a regression test.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maintain Job Radar quality feedback and review.")
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    mark = subparsers.add_parser("mark", help="Mark a radar job suitable or false-positive")
    mark.add_argument("--job-key", required=True)
    mark.add_argument("--verdict", required=True, choices=("suitable", "false-positive"))
    mark.add_argument("--notes", default="")
    missed = subparsers.add_parser("missed", help="Record a suitable vacancy missed by the radar")
    missed.add_argument("--company", required=True)
    missed.add_argument("--position", required=True)
    missed.add_argument("--url", required=True)
    missed.add_argument("--found-date", default=date.today().isoformat())
    missed.add_argument("--reason", default="")
    missed.add_argument("--notes", default="")
    subparsers.add_parser("list", help="List current manual feedback")
    subparsers.add_parser("report", help="Regenerate the rolling quality report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.project_root.resolve()
    feedback_path = root / "data/quality_feedback.json"
    report_json = root / "reports/quality_review.json"
    report_markdown = root / "reports/quality_review.md"
    generated_at = iso_now()
    try:
        feedback = normalize_quality_feedback(load_json(feedback_path, empty_feedback()))
        jobs = load_json(root / "data/jobs.json", [])
        if args.command == "mark":
            feedback = record_job_review(
                feedback,
                jobs,
                args.job_key.strip(),
                args.verdict,
                args.notes,
                generated_at,
            )
            write_json_atomic(feedback_path, feedback)
            print(f"Saved {args.verdict} review for {args.job_key.strip()}")
        elif args.command == "missed":
            feedback = record_missed_job(
                feedback,
                args.company,
                args.position,
                args.url,
                args.found_date,
                args.reason,
                args.notes,
                generated_at,
            )
            write_json_atomic(feedback_path, feedback)
            print(f"Saved missed vacancy: {args.company} | {args.position}")
        elif args.command == "list":
            if not feedback["job_reviews"] and not feedback["missed_jobs"]:
                print("No quality feedback is recorded yet.")
            for item in feedback["job_reviews"].values():
                print(f"{item['verdict']:<15} {item['company']} | {item['position']}")
            for item in feedback["missed_jobs"].values():
                print(f"{'MISSED':<15} {item['company']} | {item['position']}")
        elif args.command == "report":
            config = load_json(root / "config/search_config.json", {})
            review = build_quality_review(
                load_json(root / "data/job_history.json", {"runs": [], "events": []}),
                feedback,
                load_json(root / "data/applications.json", {}),
                jobs,
                generated_at,
                config.get("quality_review", {}),
            )
            write_json_atomic(report_json, review)
            write_text_atomic(report_markdown, render_quality_review_markdown(review))
            print(f"Wrote rolling quality review to {report_markdown}")
        return 0
    except (QualityFeedbackError, OSError) as exc:
        print(f"Quality review error: {exc}", file=sys.stderr)
        return 1


def _score_calibration(
    applications: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    minimum_outcomes: int,
) -> dict[str, Any]:
    jobs_by_key = {str(job.get("job_key")): job for job in jobs if job.get("job_key")}
    interviewed: list[dict[str, Any]] = []
    negative: list[dict[str, Any]] = []
    for application in applications:
        job = jobs_by_key.get(str(application.get("job_key")))
        if not job or not job.get("score_breakdown"):
            continue
        status = str(application.get("status") or "").upper()
        if _is_interview(application):
            interviewed.append(job)
        elif status in NEGATIVE_OUTCOMES:
            negative.append(job)
    usable = len(interviewed) + len(negative)
    if usable < minimum_outcomes or not interviewed or not negative:
        return {
            "ready": False,
            "usable_outcomes": usable,
            "interviewed_outcomes": len(interviewed),
            "negative_outcomes": len(negative),
            "message": (
                f"Insufficient outcome evidence: {usable}/{minimum_outcomes} usable outcomes, "
                f"including {len(interviewed)} interview(s) and {len(negative)} rejection/ghosting outcome(s). "
                "Do not change scoring weights yet."
            ),
            "component_deltas": {},
        }
    components = sorted(interviewed[0].get("score_breakdown", {}))
    deltas: dict[str, dict[str, float]] = {}
    for component in components:
        positive_average = _average(
            float(job.get("score_breakdown", {}).get(component, 0)) for job in interviewed
        )
        negative_average = _average(
            float(job.get("score_breakdown", {}).get(component, 0)) for job in negative
        )
        deltas[component] = {
            "interviewed_average": round(positive_average, 2),
            "negative_average": round(negative_average, 2),
            "difference": round(positive_average - negative_average, 2),
        }
    return {
        "ready": True,
        "usable_outcomes": usable,
        "interviewed_outcomes": len(interviewed),
        "negative_outcomes": len(negative),
        "message": (
            "Outcome evidence is available. Treat component differences as review signals, not proof of causation; "
            "vacancy quality, CV tailoring, timing, and German requirements can also affect interviews."
        ),
        "component_deltas": deltas,
    }


def _recommendations(
    ready: bool,
    metrics: dict[str, Any],
    calibration: dict[str, Any],
    minimum_reviewed: int,
) -> list[str]:
    if not ready:
        return [
            "Keep the current scoring weights unchanged until the required daily-run baseline is complete.",
            "Mark suitable and false-positive radar jobs and log suitable vacancies found outside the radar during every run.",
            "Maintain application and interview dates so outcome calibration becomes possible.",
        ]
    recommendations: list[str] = []
    if metrics["reviewed_jobs"] < minimum_reviewed:
        recommendations.append(
            f"Do not tune relevance yet: only {metrics['reviewed_jobs']} jobs were manually reviewed; at least {minimum_reviewed} are required for a minimally useful false-positive rate."
        )
    elif metrics["false_positive_rate_percent"] > 20:
        recommendations.append(
            "False positives exceed 20%. Inspect their shared title/location/mandatory-gap pattern and tighten that specific rule before changing global weights."
        )
    else:
        recommendations.append(
            "The reviewed false-positive rate does not justify a broad relevance-threshold change."
        )
    if metrics["missed_suitable_jobs"]:
        recommendations.append(
            "Review every logged missed vacancy and add only the missing source, title alias, location rule, or skill alias supported by those examples."
        )
    if metrics["duplicate_rate_percent"] > 15:
        recommendations.append(
            "Duplicate rate exceeds 15%; add regression fixtures for the dominant duplicate pattern before expanding sources further."
        )
    if metrics["source_failure_rate_percent"] > 10:
        recommendations.append(
            "Source failure rate exceeds 10%; prioritize identifier cleanup, cooldown tuning, or a smaller batch before scoring changes."
        )
    duration = metrics.get("average_workflow_duration_seconds")
    if duration is not None and duration > 1200:
        recommendations.append(
            "Average runtime exceeds 20 minutes; reduce daily employer coverage or worker retries before the 30-minute limit is threatened."
        )
    if not calibration.get("ready"):
        recommendations.append(
            "Keep all scoring weights unchanged because there are not enough interviewed and negative application outcomes."
        )
    else:
        useful = [
            (name, values["difference"])
            for name, values in calibration.get("component_deltas", {}).items()
            if abs(float(values["difference"])) >= 2
        ]
        if useful:
            summary = ", ".join(f"{name} ({difference:+})" for name, difference in useful)
            recommendations.append(
                "Manually review score components with outcome differences of at least two points: "
                + summary
                + ". Any weight change should be small, keep the total at 100, and include regression tests."
            )
        else:
            recommendations.append(
                "Interview outcomes do not separate score components strongly enough to justify weight changes."
            )
    return recommendations


def _outcomes_by_score_band(applications: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in applications:
        score = record.get("radar_score")
        if score is None:
            band = "UNRECORDED"
        elif int(score) >= 85:
            band = "85-100 APPLY FIRST"
        elif int(score) >= 80:
            band = "80-84 APPLY"
        elif int(score) >= 70:
            band = "70-79 REVIEW"
        else:
            band = "BELOW 70"
        groups.setdefault(band, []).append(record)
    result: dict[str, dict[str, Any]] = {}
    for band, records in groups.items():
        interviews = sum(_is_interview(record) for record in records)
        result[band] = {
            "applications": len(records),
            "interviews": interviews,
            "interview_rate_percent": _rate(interviews, len(records)),
        }
    return result


def _is_interview(record: dict[str, Any]) -> bool:
    status = str(record.get("status") or "").upper()
    return (
        APPLICATION_STAGE.get(status, 0) >= 3
        or bool(record.get("interview_date"))
        or bool(record.get("interview_stage"))
    )


def _interview_in_period(record: dict[str, Any], start: str, end: str) -> bool:
    if _in_period(record.get("interview_date"), start, end):
        return True
    return _is_interview(record) and _in_period(record.get("response_date"), start, end)


def _feedback_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_key": item.get("job_key"),
        "company": item.get("company"),
        "position": item.get("position"),
        "score": item.get("score"),
        "notes": item.get("notes"),
    }


def _in_period(value: Any, start: str, end: str) -> bool:
    if not value:
        return False
    day = str(value)[:10]
    return start <= day <= end


def _rate(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _average(values: Any) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _optional_score(value: Any, key: str) -> int | None:
    if value in {None, ""}:
        return None
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise QualityFeedbackError(f"Job review '{key}' score must be an integer") from exc
    if not 0 <= score <= 100:
        raise QualityFeedbackError(f"Job review '{key}' score must be between 0 and 100")
    return score


def _optional_date_or_datetime(value: Any, key: str, field: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    try:
        if "T" in text:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        else:
            date.fromisoformat(text)
    except ValueError as exc:
        raise QualityFeedbackError(
            f"Job review '{key}' field {field} must use ISO date or datetime format"
        ) from exc
    return text


def _validate_date(value: str, key: str, field: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise QualityFeedbackError(f"'{key}' field {field} must use YYYY-MM-DD") from exc


if __name__ == "__main__":
    raise SystemExit(main())
