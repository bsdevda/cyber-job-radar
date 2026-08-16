from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from .analysis import (
    analyze_posting_age,
    analyze_skill_requirements,
    detect_german_requirement,
    detect_skills,
    extract_experience,
)
from .analytics import build_weekly_snapshot, render_weekly_markdown, update_weekly_analytics
from .application_tracker import normalize_applications, write_application_csv
from .classification import classify_role, classify_seniority
from .collectors import (
    ArbeitnowCollector,
    AshbyCollector,
    GreenhouseCollector,
    LeverCollector,
    LinkedInPostsCollector,
    PersonioCollector,
    RecruiteeCollector,
    RemotiveCollector,
)
from .company_schedule import (
    IDENTIFIER_FIELDS,
    render_company_health_markdown,
    select_companies,
    update_company_health,
)
from .config_validation import ConfigurationError, priority_company_names, validate_companies_config
from .deduplication import deduplicate_jobs
from .eligibility import assess_location
from .filters import hard_filter, is_cybersecurity_relevant, summarize_rejections
from .normalize import content_hash, normalize_job
from .notifications import build_job_alert, render_job_alert_markdown
from .quality_review import (
    build_quality_review,
    empty_feedback,
    normalize_quality_feedback,
    render_quality_review_markdown,
)
from .reporting import (
    build_chatgpt_handoff,
    build_report_payload,
    render_markdown,
    select_report_jobs,
)
from .scoring import score_job
from .source_health import build_source_health
from .storage import append_run_history, apply_seen_tracking, merge_job_database
from .utils import HttpClient, iso_now, load_json, normalize_text, write_json_atomic, write_text_atomic


LOGGER = logging.getLogger("cyber_job_radar")


def run(
    project_root: Path,
    fixture_dir: Path | None = None,
    no_archive: bool = False,
    generated_at_override: str | None = None,
    employer_mode: str = "daily",
) -> dict[str, Any]:
    process_started = time.time()
    try:
        workflow_started = float(os.environ.get("RADAR_WORKFLOW_STARTED_EPOCH", process_started))
    except ValueError:
        workflow_started = process_started
    generated_at = generated_at_override or iso_now()
    search_config = load_json(project_root / "config/search_config.json")
    profile = load_json(project_root / "config/candidate_profile.json")
    sources_config = load_json(project_root / "config/sources.json")
    companies = validate_companies_config(
        load_json(project_root / "config/companies.json", {"priority_companies": []})
    )
    employer_scan_options = sources_config.get("employer_scan", {})
    company_health_path = project_root / "data/company_health.json"
    existing_company_health = load_json(
        company_health_path,
        {"schema_version": 1, "employers": {}},
    )

    collector_types = {
        "arbeitnow": ArbeitnowCollector,
        "remotive": RemotiveCollector,
        "greenhouse": GreenhouseCollector,
        "ashby": AshbyCollector,
        "lever": LeverCollector,
        "linkedin_posts": LinkedInPostsCollector,
        "personio": PersonioCollector,
        "recruitee": RecruiteeCollector,
    }
    results = []
    raw_jobs: list[dict[str, Any]] = []
    employer_selection: dict[str, Any] = {
        "mode": employer_mode,
        "generated_at": generated_at,
        "sources": {},
    }
    for source_name, source_options in sources_config["sources"].items():
        if not source_options.get("enabled", False):
            continue
        collector_type = collector_types.get(source_name)
        if collector_type is None:
            raise ConfigurationError(f"No collector implementation for enabled source: {source_name}")
        source_companies = companies.get(source_name, [])
        if source_name in IDENTIFIER_FIELDS:
            source_companies, selection = select_companies(
                source_name,
                source_companies,
                existing_company_health,
                generated_at,
                employer_mode,
                employer_scan_options,
                fixture_mode=fixture_dir is not None,
            )
            employer_selection["sources"][source_name] = selection
            LOGGER.info(
                "%s employer scan: %d selected, %d rotation skip(s), %d cooldown skip(s)",
                source_name,
                selection["selected"],
                selection["skipped_by_rotation"],
                selection["skipped_by_cooldown"],
            )
        client_options = {
            **sources_config["http"],
            **source_options.get("http", {}),
        }
        http = HttpClient(**client_options)
        result = collector_type(source_options, http, source_companies).collect(fixture_dir)
        results.append(result)
        raw_jobs.extend(result.jobs)
        if result.ok:
            LOGGER.info("%s: collected %d job(s)", source_name, len(result.jobs))
        else:
            LOGGER.error("%s failed: %s", source_name, result.error)
        for error in result.errors:
            LOGGER.warning("%s", error.get("message", error))

    phase_started = time.perf_counter()
    security_candidate_jobs = [
        raw for raw in raw_jobs if is_cybersecurity_relevant(raw, search_config)
    ]
    prefiltered_count = len(raw_jobs) - len(security_candidate_jobs)
    LOGGER.info(
        "Title prefilter retained %d/%d posting(s); skipped %d non-security title(s)",
        len(security_candidate_jobs),
        len(raw_jobs),
        prefiltered_count,
    )
    normalized = [normalize_job(raw) for raw in security_candidate_jobs]
    LOGGER.info(
        "Normalized %d posting(s) in %.1fs",
        len(normalized),
        time.perf_counter() - phase_started,
    )
    phase_started = time.perf_counter()
    deduped = deduplicate_jobs(normalized, search_config)
    duplicate_count = len(normalized) - len(deduped)
    LOGGER.info(
        "Deduplicated to %d posting(s) in %.1fs",
        len(deduped),
        time.perf_counter() - phase_started,
    )
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    priority_companies = priority_company_names(companies)

    phase_started = time.perf_counter()
    for index, job in enumerate(deduped, 1):
        if index % 5000 == 0:
            LOGGER.info(
                "Processed %d/%d unique postings (%d relevant so far)",
                index,
                len(deduped),
                len(accepted),
            )
        # Title relevance is intentionally checked before description-wide
        # language, experience and 60-skill analysis. Large employer boards
        # contain mostly non-security vacancies; scoring every one made the
        # workflow exceed its time limit without changing the final report.
        if not is_cybersecurity_relevant(job, search_config):
            job["rejection_reasons"] = ["Insufficient cybersecurity relevance"]
            rejected.append(job)
            continue

        german = detect_german_requirement(job["description"])
        experience = extract_experience(job["description"])
        job["german_analysis"] = german
        job["german_requirement"] = german["label"]
        job["experience_analysis"] = experience
        job["experience_required"] = experience["display"] if experience else None
        job["posting_age_analysis"] = analyze_posting_age(
            job.get("published_at", ""), generated_at
        )
        job["seniority_analysis"] = classify_seniority(job["title"])
        job["location_analysis"] = assess_location(job, search_config)
        allowed, reasons = hard_filter(job, search_config)
        if not allowed:
            job["rejection_reasons"] = reasons
            rejected.append(job)
            continue

        # The expensive evidence scan is needed only for security vacancies
        # that survived hard filters.
        skills, categories = detect_skills(
            job["description"], search_config["skill_aliases"], profile["skill_status"]
        )
        job["skills_detected"] = skills
        job["skill_matches"] = categories
        requirements = analyze_skill_requirements(
            job["description"], search_config["skill_aliases"], profile["skill_status"]
        )
        job["skill_requirements"] = requirements
        job["mandatory_gaps"] = [
            item
            for item in requirements
            if item["requirement"] == "mandatory" and item["profile_status"] in {"partial", "missing"}
        ]
        job["potential_gaps"] = [
            item
            for item in requirements
            if item["requirement"] == "mentioned" and item["profile_status"] == "missing"
        ]
        job["optional_gaps"] = [
            item
            for item in requirements
            if item["requirement"] == "optional" and item["profile_status"] in {"partial", "missing"}
        ]
        job["role_family"] = classify_role(job, search_config)
        job["priority_employer"] = normalize_text(job["company"]) in priority_companies
        job["content_hash"] = content_hash(job)
        score_job(job, search_config, profile)
        if job["score"] < int(search_config["relevant_score"]):
            job["rejection_reasons"] = [f"Score below relevance threshold ({job['score']} < {search_config['relevant_score']})"]
            rejected.append(job)
            continue
        accepted.append(job)
    LOGGER.info(
        "Filtered and scored %d posting(s) in %.1fs",
        len(deduped),
        time.perf_counter() - phase_started,
    )

    now = generated_at
    data_dir = project_root / "data"
    previous_jobs = load_json(data_dir / "jobs.json", [])
    seen = load_json(data_dir / "seen_jobs.json", {})
    applications = normalize_applications(
        load_json(data_dir / "applications.json", {}),
        previous_jobs,
        now,
    )
    history = load_json(data_dir / "job_history.json", {"runs": [], "events": []})
    source_health = build_source_health(results, now)
    source_health["employer_scan"] = employer_selection
    company_health = update_company_health(
        existing_company_health,
        companies,
        results,
        employer_selection,
        now,
        employer_scan_options,
    )
    source_status = source_health["sources"]
    seen, events = apply_seen_tracking(
        accepted,
        seen,
        now,
        int(search_config["expire_after_days"]),
        allow_expiry=any(
            details["status"] in {"ok", "partial"} for details in source_status.values()
        ),
    )
    jobs_db = merge_job_database(previous_jobs, accepted, seen)
    for job in jobs_db:
        application = applications.get(job["job_key"], {})
        job["application_status"] = application.get("status", "NEW")

    # The daily scoring summary remains based on this run's accepted jobs, but
    # the reading queue is selected from the active cumulative database. This
    # keeps up to 50 still-active matches visible even when a rotating employer
    # batch yields fewer jobs on a particular day.
    report_jobs = select_report_jobs(jobs_db, search_config)
    payload = build_report_payload(
        report_jobs,
        accepted,
        source_status,
        len(raw_jobs),
        len(security_candidate_jobs),
        duplicate_count,
        len(rejected) + prefiltered_count,
        now,
        search_config,
    )
    payload["summary"]["employer_mode"] = employer_mode
    payload["summary"]["quality_review_schema_version"] = 1
    payload["summary"]["workflow_duration_seconds"] = round(
        max(0.0, time.time() - workflow_started), 1
    )
    payload["all_sources_failed"] = source_health["all_sources_failed"]
    payload["employer_scan"] = employer_selection
    payload["rejection_summary"] = summarize_rejections(rejected)
    run_summary = {**payload["summary"], "source_status": source_status}
    history = append_run_history(
        history, run_summary, events, int(search_config["history_run_limit"])
    )
    quality_feedback = normalize_quality_feedback(
        load_json(data_dir / "quality_feedback.json", empty_feedback())
    )
    quality_review = build_quality_review(
        history,
        quality_feedback,
        applications,
        jobs_db,
        now,
        search_config.get("quality_review", {}),
    )
    job_alert = build_job_alert(accepted, search_config, now)
    handoff = build_chatgpt_handoff(
        report_jobs,
        profile,
        source_status,
        payload["summary"],
        now,
        int(search_config.get("chatgpt_handoff_limit", 10)),
    )
    weekly_snapshot = build_weekly_snapshot(accepted, applications, now)
    weekly_analytics = update_weekly_analytics(
        load_json(data_dir / "weekly_analytics.json", {"snapshots": []}),
        weekly_snapshot,
        int(search_config.get("weekly_history_limit", 104)),
    )

    write_json_atomic(data_dir / "jobs.json", jobs_db)
    write_json_atomic(data_dir / "seen_jobs.json", seen)
    write_json_atomic(data_dir / "job_history.json", history)
    write_json_atomic(data_dir / "quality_feedback.json", quality_feedback)
    write_json_atomic(data_dir / "source_health.json", source_health)
    write_json_atomic(company_health_path, company_health)
    write_json_atomic(data_dir / "applications.json", applications)
    write_json_atomic(data_dir / "weekly_analytics.json", weekly_analytics)
    write_json_atomic(project_root / "reports/latest.json", payload)
    write_json_atomic(project_root / "reports/chatgpt_handoff.json", handoff)
    write_json_atomic(project_root / "reports/job_alert.json", job_alert)
    write_json_atomic(project_root / "reports/quality_review.json", quality_review)
    markdown = render_markdown(payload, search_config)
    write_text_atomic(project_root / "reports/latest.md", markdown)
    write_text_atomic(project_root / "reports/weekly.md", render_weekly_markdown(weekly_analytics))
    write_text_atomic(
        project_root / "reports/job_alert.md", render_job_alert_markdown(job_alert)
    )
    write_text_atomic(
        project_root / "reports/quality_review.md",
        render_quality_review_markdown(quality_review),
    )
    write_application_csv(project_root / "reports/application_tracker.csv", applications)
    write_text_atomic(
        project_root / "reports/company_health.md",
        render_company_health_markdown(company_health),
    )
    if not no_archive:
        write_text_atomic(project_root / f"reports/archive/{now[:10]}.md", markdown)
    LOGGER.info(
        "Run complete: %d collected, %d relevant, %d rejected, %d duplicate(s)",
        len(raw_jobs),
        len(accepted),
        len(rejected) + prefiltered_count,
        duplicate_count,
    )
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect and score cybersecurity vacancies.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project directory containing config/, data/, and reports/.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        help="Read provider payloads from arbeitnow.json/remotive.json instead of the network.",
    )
    parser.add_argument("--no-archive", action="store_true", help="Do not write a dated Markdown archive.")
    parser.add_argument(
        "--employer-mode",
        choices=("daily", "full"),
        default="daily",
        help="Use the daily rotating employer batch or the complete employer watchlist.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        payload = run(
            args.project_root.resolve(),
            args.fixture_dir.resolve() if args.fixture_dir else None,
            args.no_archive,
            employer_mode=args.employer_mode,
        )
    except Exception:
        LOGGER.exception("Radar run failed")
        return 1
    if payload.get("all_sources_failed"):
        LOGGER.error("All operational sources failed; reports were written for diagnosis")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
