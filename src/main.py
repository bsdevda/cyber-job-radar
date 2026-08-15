from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

from .analysis import (
    analyze_skill_requirements,
    detect_german_requirement,
    detect_skills,
    extract_experience,
)
from .analytics import build_weekly_snapshot, render_weekly_markdown, update_weekly_analytics
from .classification import classify_role, classify_seniority
from .collectors import (
    ArbeitnowCollector,
    AshbyCollector,
    GreenhouseCollector,
    LeverCollector,
    PersonioCollector,
    RemotiveCollector,
)
from .config_validation import ConfigurationError, priority_company_names, validate_companies_config
from .deduplication import deduplicate_jobs
from .eligibility import assess_location
from .filters import hard_filter, summarize_rejections
from .normalize import content_hash, normalize_job
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


def run(project_root: Path, fixture_dir: Path | None = None, no_archive: bool = False) -> dict[str, Any]:
    search_config = load_json(project_root / "config/search_config.json")
    profile = load_json(project_root / "config/candidate_profile.json")
    sources_config = load_json(project_root / "config/sources.json")
    companies = validate_companies_config(
        load_json(project_root / "config/companies.json", {"priority_companies": []})
    )
    http = HttpClient(**sources_config["http"])

    collector_types = {
        "arbeitnow": ArbeitnowCollector,
        "remotive": RemotiveCollector,
        "greenhouse": GreenhouseCollector,
        "ashby": AshbyCollector,
        "lever": LeverCollector,
        "personio": PersonioCollector,
    }
    results = []
    raw_jobs: list[dict[str, Any]] = []
    for source_name, source_options in sources_config["sources"].items():
        if not source_options.get("enabled", False):
            continue
        collector_type = collector_types.get(source_name)
        if collector_type is None:
            raise ConfigurationError(f"No collector implementation for enabled source: {source_name}")
        result = collector_type(source_options, http, companies.get(source_name, [])).collect(fixture_dir)
        results.append(result)
        raw_jobs.extend(result.jobs)
        if result.ok:
            LOGGER.info("%s: collected %d job(s)", source_name, len(result.jobs))
        else:
            LOGGER.error("%s failed: %s", source_name, result.error)
        for error in result.errors:
            LOGGER.warning("%s", error.get("message", error))

    normalized = [normalize_job(raw) for raw in raw_jobs]
    deduped = deduplicate_jobs(normalized)
    duplicate_count = len(normalized) - len(deduped)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    priority_companies = priority_company_names(companies)

    for job in deduped:
        job["content_hash"] = content_hash(job)
        german = detect_german_requirement(job["description"])
        experience = extract_experience(job["description"])
        skills, categories = detect_skills(
            job["description"], search_config["skill_aliases"], profile["skill_status"]
        )
        job["german_analysis"] = german
        job["german_requirement"] = german["label"]
        job["experience_analysis"] = experience
        job["experience_required"] = experience["display"] if experience else None
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
        job["seniority_analysis"] = classify_seniority(job["title"])
        job["location_analysis"] = assess_location(job, search_config)
        job["priority_employer"] = normalize_text(job["company"]) in priority_companies
        allowed, reasons = hard_filter(job, search_config)
        if not allowed:
            job["rejection_reasons"] = reasons
            rejected.append(job)
            continue
        score_job(job, search_config, profile)
        if job["score"] < int(search_config["relevant_score"]):
            job["rejection_reasons"] = [f"Score below relevance threshold ({job['score']} < {search_config['relevant_score']})"]
            rejected.append(job)
            continue
        accepted.append(job)

    now = iso_now()
    data_dir = project_root / "data"
    previous_jobs = load_json(data_dir / "jobs.json", [])
    seen = load_json(data_dir / "seen_jobs.json", {})
    applications = load_json(data_dir / "applications.json", {})
    history = load_json(data_dir / "job_history.json", {"runs": [], "events": []})
    source_health = build_source_health(results, now)
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
    for job in accepted:
        application = applications.get(job["job_key"], {})
        job["application_status"] = application.get("status", "NEW")

    report_jobs = select_report_jobs(accepted, search_config)
    payload = build_report_payload(
        report_jobs,
        accepted,
        source_status,
        len(raw_jobs),
        duplicate_count,
        len(rejected),
        now,
        search_config,
    )
    payload["all_sources_failed"] = source_health["all_sources_failed"]
    payload["rejection_summary"] = summarize_rejections(rejected)
    run_summary = {**payload["summary"], "source_status": source_status}
    history = append_run_history(
        history, run_summary, events, int(search_config["history_run_limit"])
    )
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
    write_json_atomic(data_dir / "source_health.json", source_health)
    write_json_atomic(data_dir / "weekly_analytics.json", weekly_analytics)
    write_json_atomic(project_root / "reports/latest.json", payload)
    write_json_atomic(project_root / "reports/chatgpt_handoff.json", handoff)
    markdown = render_markdown(payload, search_config)
    write_text_atomic(project_root / "reports/latest.md", markdown)
    write_text_atomic(project_root / "reports/weekly.md", render_weekly_markdown(weekly_analytics))
    if not no_archive:
        write_text_atomic(project_root / f"reports/archive/{now[:10]}.md", markdown)
    LOGGER.info(
        "Run complete: %d collected, %d relevant, %d rejected, %d duplicate(s)",
        len(raw_jobs), len(accepted), len(rejected), duplicate_count,
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
