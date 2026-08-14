from __future__ import annotations

from collections import Counter
from typing import Any

from .scoring import recommendation


def select_report_jobs(jobs: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    active = [job for job in jobs if job.get("status") != "REMOVED"]
    fresh = sorted(
        (job for job in active if job.get("status") in {"NEW", "UPDATED"}),
        key=lambda job: (int(job.get("score", 0)), job.get("published_at", "")),
        reverse=True,
    )
    selected = fresh[: int(config["report_limit"])]
    if config.get("include_seen_fallback") and len(selected) < int(config["report_limit"]):
        selected_keys = {job["job_key"] for job in selected}
        seen = sorted(
            (job for job in active if job["job_key"] not in selected_keys),
            key=lambda job: (int(job.get("score", 0)), job.get("last_seen", "")),
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
) -> dict[str, Any]:
    status_counts = Counter(job.get("status", "") for job in all_relevant_jobs)
    summary = {
        "generated_at": generated_at,
        "jobs_collected": collected_count,
        "unique_jobs_after_deduplication": collected_count - duplicate_count,
        "duplicates_removed": duplicate_count,
        "jobs_rejected_or_below_threshold": rejected_count,
        "relevant_jobs_in_current_run": len(all_relevant_jobs),
        "new_jobs": status_counts["NEW"],
        "updated_jobs": status_counts["UPDATED"],
        "strong_matches": sum(job.get("score", 0) >= 80 for job in all_relevant_jobs),
        "sources_checked": len(source_status),
        "sources_failed": sum(
            details.get("status") == "failed" for details in source_status.values()
        ),
        "sources_partial": sum(
            details.get("status") == "partial" for details in source_status.values()
        ),
        "report_jobs": len(jobs),
        "jobs_by_source": {
            source: details.get("jobs", 0) for source, details in source_status.items()
        },
    }
    compact_jobs = []
    for number, job in enumerate(jobs, start=1):
        compact_jobs.append(
            {
                "report_number": number,
                "job_key": job["job_key"],
                "status": job.get("status"),
                "score": job.get("score"),
                "score_label": job.get("score_label"),
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "working_model": working_model(job),
                "url": job.get("url"),
                "apply_url": job.get("apply_url"),
                "canonical_url": job.get("canonical_url"),
                "source": job.get("source"),
                "sources": job.get("sources", []),
                "original_source": job.get("source"),
                "ats": job.get("ats", ""),
                "also_found_on": [
                    source for source in job.get("sources", []) if source != job.get("source")
                ],
                "priority_employer": bool(job.get("priority_employer")),
                "published_at": job.get("published_at"),
                "first_seen": job.get("first_seen"),
                "experience_required": job.get("experience_required"),
                "german_requirement": job.get("german_requirement"),
                "skill_matches": job.get("skill_matches", {}),
                "score_breakdown": job.get("score_breakdown", {}),
                "match_reasons": job.get("match_reasons", []),
                "warnings": job.get("warnings", []),
                "recommendation": recommendation(int(job.get("score", 0))),
                "application_status": job.get("application_status", "NEW"),
                "description_excerpt": _description_excerpt(job.get("description", "")),
            }
        )
    return {"generated_at": generated_at, "summary": summary, "jobs": compact_jobs, "source_status": source_status}


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    date = payload["generated_at"][:10]
    lines = [
        "# Cybersecurity Job Radar",
        "",
        f"**Date:** {date}",
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
        "> Scores are a transparent first filter, not an application decision. Verify the original vacancy before tailoring a CV.",
        "",
        "## Jobs Collected by Source",
        "",
    ]
    for source, count in summary["jobs_by_source"].items():
        lines.append(f"- **{source.title()}:** {count}")
    lines.append("")
    jobs = payload["jobs"]
    sections = [
        ("🔥 APPLY FIRST", lambda score: score >= 90),
        ("🟢 STRONG MATCHES", lambda score: 70 <= score < 90),
        ("🟡 REVIEW", lambda score: 60 <= score < 70),
        ("🟠 STRETCH", lambda score: 50 <= score < 60),
    ]
    for heading, predicate in sections:
        section_jobs = [job for job in jobs if predicate(int(job.get("score", 0)))]
        lines.extend([f"## {heading}", ""])
        if not section_jobs:
            lines.extend(["No jobs in this section today.", ""])
            continue
        for job in section_jobs:
            lines.extend(_render_job(job))

    lines.extend(["## Source Health", ""])
    for source, details in payload["source_status"].items():
        status = details.get("status", "failed")
        icon = {"ok": "✅", "partial": "⚠️", "failed": "❌", "idle": "◻️"}.get(status, "❓")
        if "companies_checked" in details:
            checked = details.get("companies_checked", 0)
            successful = details.get("companies_successful", 0)
            label = (
                "no enabled companies"
                if status == "idle"
                else f"{successful}/{checked} companies successful, {details.get('jobs', 0)} jobs"
            )
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
            "Upload or link both `reports/latest.md` and `data/jobs.json`, then ask: `Analyze job #1 against my actual CV. Verify the original requirements and recommend APPLY, REVIEW, or SKIP without inventing experience.`",
            "",
        ]
    )
    return "\n".join(lines)


def _render_job(job: dict[str, Any]) -> list[str]:
    strong = job.get("skill_matches", {}).get("match", [])
    partial = job.get("skill_matches", {}).get("partial", [])
    missing = job.get("skill_matches", {}).get("missing", [])
    nice = job.get("skill_matches", {}).get("nice_to_have", [])
    also_found_on = ", ".join(job.get("also_found_on", [])) or "No other source"
    ats = str(job.get("ats") or "Not identified").title()
    return [
        f"### {job['report_number']}. {_clean(job.get('title', 'Untitled role'))}",
        "",
        f"- **Company:** {_clean(job.get('company', 'Unknown'))}",
        f"- **Location:** {_clean(job.get('location', 'Unspecified'))}",
        f"- **Working model:** {job.get('working_model')}",
        f"- **Source:** {_clean(job.get('source', 'Unknown'))}",
        f"- **Original source:** {_clean(job.get('original_source', job.get('source', 'Unknown')))}",
        f"- **ATS:** {ats}",
        f"- **Also found on:** {also_found_on}",
        f"- **Priority employer:** {'YES' if job.get('priority_employer') else 'NO'}",
        f"- **Posted:** {(job.get('published_at') or 'Unknown')[:10]}",
        f"- **First seen:** {(job.get('first_seen') or 'Unknown')[:10]}",
        f"- **Radar status:** {job.get('status')}",
        f"- **Application status:** {job.get('application_status')}",
        f"- **Match score:** **{job.get('score')}/100 - {job.get('score_label')}**",
        f"- **Direct job URL:** [{_clean(job.get('company', 'Open job'))} vacancy]({job.get('url')})",
        "",
        "**Strong matches:** " + (_join(strong) or "None detected"),
        "",
        "**Partial matches:** " + (_join(partial) or "None detected"),
        "",
        "**Potential gaps:** " + (_join(missing) or "None detected"),
        "",
        "**Nice-to-have requirements:** " + (_join(nice) or "None detected"),
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


def _description_excerpt(description: str, limit: int = 1200) -> str:
    compact = " ".join(description.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def _clean(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|").strip()


def _join(values: list[str]) -> str:
    return ", ".join(_clean(value) for value in values[:10])
