from __future__ import annotations

from collections import Counter
from typing import Any

from .analysis import analyze_posting_age
from .scoring import recommendation


def select_report_jobs(jobs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    excluded_statuses = {
        str(status).upper() for status in config.get("report_excluded_application_statuses", [])
    }
    active = [
        job
        for job in jobs
        if job.get("status") != "REMOVED"
        and str(job.get("application_status", "NEW")).upper() not in excluded_statuses
    ]
    sort_key = lambda job: (
        int(job.get("score", 0)),
        bool(job.get("priority_employer")),
        job.get("published_at", ""),
    )
    fresh = sorted(
        (job for job in active if job.get("status") in {"NEW", "UPDATED"}),
        key=sort_key,
        reverse=True,
    )
    selected = fresh[: int(config["report_limit"])]
    if config.get("include_seen_fallback") and len(selected) < int(config["report_limit"]):
        selected_keys = {job["job_key"] for job in selected}
        seen = sorted(
            (job for job in active if job["job_key"] not in selected_keys),
            key=sort_key,
            reverse=True,
        )
        selected.extend(seen[: int(config["report_limit"]) - len(selected)])
    return selected


def build_report_payload(
    jobs: list[dict[str, Any]],
    all_relevant_jobs: list[dict[str, Any]],
    source_status: dict[str, dict[str, Any]],
    collected_count: int,
    duplicate_count: int,
    rejected_count: int,
    generated_at: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    status_counts = Counter(job.get("status", "") for job in all_relevant_jobs)
    strong_threshold = int(config.get("strong_match_score", 80))
    summary = {
        "generated_at": generated_at,
        "scoring_version": config.get("scoring_version", 2),
        "jobs_collected": collected_count,
        "unique_jobs_after_deduplication": collected_count - duplicate_count,
        "duplicates_removed": duplicate_count,
        "jobs_rejected_or_below_threshold": rejected_count,
        "relevant_jobs_in_current_run": len(all_relevant_jobs),
        "new_jobs": status_counts["NEW"],
        "updated_jobs": status_counts["UPDATED"],
        "strong_matches": sum(job.get("score", 0) >= strong_threshold for job in all_relevant_jobs),
        "sources_checked": len(source_status),
        "sources_failed": sum(details.get("status") == "failed" for details in source_status.values()),
        "sources_partial": sum(details.get("status") == "partial" for details in source_status.values()),
        "report_jobs": len(jobs),
        "jobs_by_source": {
            source: details.get("jobs", 0) for source, details in source_status.items()
        },
    }
    compact_jobs = [_compact_job(job, number, generated_at) for number, job in enumerate(jobs, 1)]
    return {
        "schema_version": 2,
        "generated_at": generated_at,
        "summary": summary,
        "jobs": compact_jobs,
        "source_status": source_status,
    }


def build_chatgpt_handoff(
    jobs: list[dict[str, Any]],
    profile: dict[str, Any],
    source_status: dict[str, dict[str, Any]],
    summary: dict[str, Any],
    generated_at: str,
    limit: int,
) -> dict[str, Any]:
    selected = jobs[:limit]
    handoff_jobs: list[dict[str, Any]] = []
    for number, job in enumerate(selected, 1):
        item = _compact_job(job, number, generated_at)
        item["full_description"] = job.get("description", "")
        item["skill_requirements"] = job.get("skill_requirements", [])
        item["german_analysis"] = job.get("german_analysis", {})
        item["experience_analysis"] = job.get("experience_analysis")
        handoff_jobs.append(item)

    safe_profile = {
        "profile_version": profile.get("profile_version"),
        "last_verified": profile.get("last_verified"),
        "summary": profile.get("summary"),
        "experience_years": profile.get("experience_years"),
        "professional_evidence": profile.get("professional_evidence", {}),
        "education": profile.get("education", []),
        "languages": profile.get("languages", {}),
        "target_locations": profile.get("target_locations", []),
        "target_role_families": profile.get("target_role_families", []),
        "skill_status": profile.get("skill_status", {}),
        "skill_evidence": profile.get("skill_evidence", {}),
        "truthful_constraints": profile.get("truthful_constraints", []),
        "honesty_note": profile.get("honesty_note", ""),
    }
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "purpose": "Single-file private handoff for final human/ChatGPT vacancy analysis.",
        "privacy": "Contains sanitized professional evidence only; no CV, email, phone, photo, address or identity documents.",
        "candidate_profile": safe_profile,
        "radar_summary": summary,
        "source_status": source_status,
        "jobs": handoff_jobs,
        "analysis_request": {
            "instruction": "Review each vacancy against the supplied professional evidence. Do not trust the automated score without checking the full description.",
            "return_for_each_job": [
                "APPLY FIRST / APPLY / REVIEW / STRETCH / SKIP",
                "evidence-based fit percentage",
                "mandatory and optional gaps",
                "location and work-eligibility risk",
                "truthful CV tailoring",
                "three likely interview questions with evidence-backed answer angles"
            ],
            "never_invent": [
                "production-depth AWS, Kubernetes, cloud, CI/CD or programming experience",
                "management experience",
                "certifications or German level not present in the profile",
                "security tools or responsibilities not supported by evidence"
            ]
        }
    }


def render_markdown(payload: dict[str, Any], config: dict[str, Any]) -> str:
    summary = payload["summary"]
    date = payload["generated_at"][:10]
    lines = [
        "# Cybersecurity Job Radar",
        "",
        f"**Date:** {date}",
        f"**Scoring model:** v{summary.get('scoring_version', 2)}",
        f"**Raw postings collected:** {summary['jobs_collected']}",
        f"**Unique jobs after deduplication:** {summary['unique_jobs_after_deduplication']}",
        f"**New jobs:** {summary['new_jobs']}",
        f"**Updated jobs:** {summary['updated_jobs']}",
        f"**Relevant jobs:** {summary['relevant_jobs_in_current_run']}",
        f"**Strong matches:** {summary['strong_matches']}",
        f"**Sources checked:** {summary['sources_checked']}",
        f"**Sources failed:** {summary['sources_failed']}",
        f"**Sources partially successful:** {summary['sources_partial']}",
        "",
        "> The score is a transparent first filter. Verify the original vacancy before tailoring a CV or applying.",
        "",
        "## Jobs Collected by Source",
        "",
    ]
    for source, count in summary["jobs_by_source"].items():
        lines.append(f"- **{source.title()}:** {count}")
    lines.append("")

    jobs = payload["jobs"]
    apply_limit = int(config.get("markdown_apply_first_limit", 5))
    top_match_score = int(config.get("markdown_top_match_score", 75))
    review_limit = int(config.get("markdown_review_limit", 5))
    apply_jobs = [job for job in jobs if int(job.get("score", 0)) >= top_match_score][:apply_limit]
    apply_keys = {job["job_key"] for job in apply_jobs}
    review_jobs = [job for job in jobs if job["job_key"] not in apply_keys][:review_limit]
    for heading, section_jobs in (("🔥 TOP MATCHES", apply_jobs), ("🟡 REVIEW NEXT", review_jobs)):
        lines.extend([f"## {heading}", ""])
        if not section_jobs:
            lines.extend(["No jobs in this section today.", ""])
        else:
            for job in section_jobs:
                lines.extend(_render_job(job))

    hidden = max(0, len(jobs) - len(apply_jobs) - len(review_jobs))
    lines.extend(
        [
            "## Remaining candidates",
            "",
            f"{hidden} additional ranked jobs are available in `reports/latest.json`; the daily Markdown intentionally stays limited to the most actionable queue.",
            "",
            "## Source Health",
            "",
        ]
    )
    for source, details in payload["source_status"].items():
        status = details.get("status", "failed")
        icon = {"ok": "✅", "partial": "⚠️", "failed": "❌", "idle": "◻️"}.get(status, "❓")
        if "companies_checked" in details:
            checked = details.get("companies_checked", 0)
            successful = details.get("companies_successful", 0)
            label = "no enabled companies" if status == "idle" else f"{successful}/{checked} companies successful, {details.get('jobs', 0)} jobs"
        else:
            label = f"{details.get('jobs', 0)} jobs"
        lines.append(f"- {icon} **{source.title()}** — {label}")
        for error in details.get("errors", [])[:3]:
            lines.append(f"  - {_clean(error.get('message') or error.get('description'))}")
    lines.extend(
        [
            "",
            "## ChatGPT Handoff",
            "",
            "Upload only `reports/chatgpt_handoff.json`. It contains the sanitized candidate evidence, the top vacancies, their full descriptions, URLs and automated analysis.",
            "",
        ]
    )
    return "\n".join(lines)


def _compact_job(job: dict[str, Any], number: int, generated_at: str) -> dict[str, Any]:
    age_analysis = job.get("posting_age_analysis") or analyze_posting_age(
        job.get("published_at", ""), generated_at
    )
    age = age_analysis.get("age_days")
    urgency = age_analysis.get("label", "POSTING DATE UNKNOWN")
    return {
        "report_number": number,
        "job_key": job["job_key"],
        "status": job.get("status"),
        "application_status": job.get("application_status", "NEW"),
        "score": job.get("score"),
        "raw_score": job.get("raw_score"),
        "score_cap": job.get("score_cap"),
        "score_cap_reasons": job.get("score_cap_reasons", []),
        "score_label": job.get("score_label"),
        "title": job.get("title"),
        "company": job.get("company"),
        "location": job.get("location"),
        "location_analysis": job.get("location_analysis", {}),
        "working_model": working_model(job),
        "role_family": job.get("role_family", {}),
        "seniority": job.get("seniority_analysis", {}),
        "url": job.get("url"),
        "apply_url": job.get("apply_url"),
        "canonical_url": job.get("canonical_url"),
        "source": job.get("source"),
        "sources": job.get("sources", []),
        "ats": job.get("ats", ""),
        "priority_employer": bool(job.get("priority_employer")),
        "published_at": job.get("published_at"),
        "posting_age_days": age,
        "posting_age_analysis": age_analysis,
        "urgency": urgency,
        "first_seen": job.get("first_seen"),
        "experience_required": job.get("experience_required"),
        "german_requirement": job.get("german_requirement"),
        "skill_matches": job.get("skill_matches", {}),
        "mandatory_gaps": job.get("mandatory_gaps", []),
        "potential_gaps": job.get("potential_gaps", []),
        "optional_gaps": job.get("optional_gaps", []),
        "score_breakdown": job.get("score_breakdown", {}),
        "match_reasons": job.get("match_reasons", []),
        "warnings": job.get("warnings", []),
        "recommendation": recommendation(int(job.get("score", 0))),
        "description_excerpt": _description_excerpt(job.get("description", "")),
    }


def _render_job(job: dict[str, Any]) -> list[str]:
    strong = job.get("skill_matches", {}).get("match", [])
    partial = job.get("skill_matches", {}).get("partial", [])
    mandatory = [item.get("skill", "") for item in job.get("mandatory_gaps", [])]
    potential = [item.get("skill", "") for item in job.get("potential_gaps", [])]
    optional = [item.get("skill", "") for item in job.get("optional_gaps", [])]
    role = job.get("role_family", {})
    seniority = job.get("seniority", {})
    return [
        f"### {job['report_number']}. {_clean(job.get('title', 'Untitled role'))}",
        "",
        f"- **Company:** {_clean(job.get('company', 'Unknown'))}",
        f"- **Location:** {_clean(job.get('location', 'Unspecified'))}",
        f"- **Location eligibility:** {_clean(job.get('location_analysis', {}).get('reason', 'Unclear'))}",
        f"- **Working model:** {job.get('working_model')}",
        f"- **Role family:** {_clean(role.get('label', 'Other Security'))}",
        f"- **Seniority:** {_clean(seniority.get('label', 'Unspecified'))}",
        f"- **Source / ATS:** {_clean(job.get('source', 'Unknown'))} / {_clean(str(job.get('ats') or 'Not identified').title())}",
        f"- **Priority employer:** {'YES' if job.get('priority_employer') else 'NO'}",
        f"- **Posted:** {(job.get('published_at') or 'Unknown')[:10]} ({job.get('urgency')})",
        f"- **First seen:** {(job.get('first_seen') or 'Unknown')[:10]}",
        f"- **Radar / application status:** {job.get('status')} / {job.get('application_status')}",
        f"- **Match score:** **{job.get('score')}/100 - {job.get('score_label')}**",
        f"- **Direct job URL:** [{_clean(job.get('company', 'Open job'))} vacancy]({job.get('url')})",
        "",
        "**Strong matches:** " + (_join(strong) or "None detected"),
        "",
        "**Partial matches:** " + (_join(partial) or "None detected"),
        "",
        "**Mandatory gaps:** " + (_join(mandatory) or "None explicitly detected"),
        "",
        "**Potential gaps:** " + (_join(potential) or "None detected"),
        "",
        "**Optional gaps:** " + (_join(optional) or "None detected"),
        "",
        f"**Experience:** {job.get('experience_required') or 'No explicit years detected'}",
        "",
        f"**German:** {job.get('german_requirement')}",
        "",
        "**Why relevant:** " + " ".join(job.get("match_reasons", [])),
        "",
        "**Warnings:** " + (" ".join(job.get("warnings", [])) or "No major automated warning."),
        "",
        f"**Recommendation:** {job.get('recommendation')}",
        "",
    ]


def working_model(job: dict[str, Any]) -> str:
    if job.get("hybrid"):
        return "Hybrid"
    if job.get("remote"):
        return "Remote"
    return "On-site / not specified"


def posting_age(published_at: str, generated_at: str) -> tuple[int | None, str]:
    analysis = analyze_posting_age(published_at, generated_at)
    return analysis.get("age_days"), analysis.get("label", "POSTING DATE UNKNOWN")


def _description_excerpt(description: str, limit: int = 1200) -> str:
    compact = " ".join(description.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _clean(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|").strip()


def _join(values: list[str]) -> str:
    return ", ".join(_clean(value) for value in values[:10])
