from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any


APPLICATION_STAGE = {
    "APPLIED": 1,
    "RECRUITER CONTACT": 2,
    "PHONE SCREEN": 2,
    "INTERVIEW": 3,
    "TECHNICAL INTERVIEW": 3,
    "FINAL INTERVIEW": 4,
    "OFFER": 5,
    "REJECTED": 1,
    "GHOSTED": 1,
    "WITHDRAWN": 1,
}


def build_weekly_snapshot(
    jobs: list[dict[str, Any]],
    applications: dict[str, dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    current_date = date.fromisoformat(generated_at[:10])
    week_start = current_date - timedelta(days=current_date.weekday())
    active = [job for job in jobs if job.get("status") != "REMOVED"]
    role_counts = Counter(job.get("role_family", {}).get("label", "Other Security") for job in active)
    score_bands = Counter(_score_band(int(job.get("score", 0))) for job in active)
    mandatory = Counter()
    potential = Counter()
    optional = Counter()
    partial = Counter()
    for job in active:
        for item in job.get("mandatory_gaps", []):
            mandatory[item.get("skill", "unknown")] += 1
        for item in job.get("potential_gaps", []):
            potential[item.get("skill", "unknown")] += 1
        for item in job.get("optional_gaps", []):
            optional[item.get("skill", "unknown")] += 1
        for skill in job.get("skill_matches", {}).get("partial", []):
            partial[skill] += 1

    statuses = Counter(
        str(application.get("status", "NEW")).upper() for application in applications.values()
    )
    applied = 0
    responses = 0
    interviews = 0
    offers = 0
    for application in applications.values():
        status = str(application.get("status", "NEW")).upper()
        stage = APPLICATION_STAGE.get(status, 0)
        submitted = stage >= 1 or bool(application.get("applied_date"))
        responded = stage >= 2 or bool(application.get("response_date"))
        interviewed = stage >= 3 or bool(application.get("interview_date"))
        offered = stage >= 5 or str(application.get("final_result", "")).upper() == "OFFER"
        applied += bool(submitted)
        responses += bool(responded)
        interviews += bool(interviewed)
        offers += bool(offered)
    funnel = {
        "tracked_records": len(applications),
        "status_counts": dict(statuses.most_common()),
        "applications_submitted": applied,
        "responses_or_screens": responses,
        "interviews": interviews,
        "offers": offers,
        "response_rate_percent": _rate(responses, applied),
        "interview_rate_percent": _rate(interviews, applied),
        "offer_rate_percent": _rate(offers, applied),
    }
    return {
        "week_start": week_start.isoformat(),
        "generated_at": generated_at,
        "active_relevant_jobs": len(active),
        "role_family_counts": dict(role_counts.most_common()),
        "score_bands": dict(score_bands.most_common()),
        "skill_gaps": {
            "mandatory": _top(mandatory),
            "potential": _top(potential),
            "optional": _top(optional),
            "partial_exposure": _top(partial),
        },
        "application_funnel": funnel,
    }


def update_weekly_analytics(
    existing: dict[str, Any],
    snapshot: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    snapshots = [
        item for item in existing.get("snapshots", []) if item.get("week_start") != snapshot["week_start"]
    ]
    snapshots.append(snapshot)
    snapshots.sort(key=lambda item: item.get("week_start", ""))
    return {
        "schema_version": 1,
        "latest_week": snapshot["week_start"],
        "snapshots": snapshots[-limit:],
    }


def render_weekly_markdown(analytics: dict[str, Any]) -> str:
    snapshots = analytics.get("snapshots", [])
    if not snapshots:
        return "# Weekly Job Radar Analytics\n\nNo weekly data is available yet.\n"
    latest = snapshots[-1]
    funnel = latest["application_funnel"]
    lines = [
        "# Weekly Job Radar Analytics",
        "",
        f"**Week starting:** {latest['week_start']}",
        f"**Generated:** {latest['generated_at']}",
        f"**Active relevant jobs:** {latest['active_relevant_jobs']}",
        "",
        "## Role-family demand",
        "",
    ]
    lines.extend(_mapping_lines(latest.get("role_family_counts", {}), "No role-family data."))
    lines.extend(["", "## Skill-gap signals", ""])
    for category, label in (
        ("mandatory", "Explicit mandatory gaps"),
        ("potential", "Potential gaps"),
        ("optional", "Optional gaps"),
        ("partial_exposure", "Exposure-only skills"),
    ):
        lines.append(f"### {label}")
        lines.append("")
        values = latest.get("skill_gaps", {}).get(category, [])
        if values:
            lines.extend(f"- **{item['skill']}:** {item['jobs']} job(s)" for item in values)
        else:
            lines.append("No data yet.")
        lines.append("")
    lines.extend(
        [
            "## Application funnel",
            "",
            f"- **Applications submitted:** {funnel['applications_submitted']}",
            f"- **Responses or screens:** {funnel['responses_or_screens']} ({funnel['response_rate_percent']}%)",
            f"- **Interviews:** {funnel['interviews']} ({funnel['interview_rate_percent']}%)",
            f"- **Offers:** {funnel['offers']} ({funnel['offer_rate_percent']}%)",
            "",
            "Update `data/applications.json` after each application or recruiter interaction; otherwise funnel rates remain zero.",
            "",
        ]
    )
    return "\n".join(lines)


def _score_band(score: int) -> str:
    if score >= 80:
        return "80-100 strong"
    if score >= 70:
        return "70-79 good"
    if score >= 60:
        return "60-69 review"
    return "50-59 stretch"


def _top(counter: Counter[str], limit: int = 12) -> list[dict[str, Any]]:
    return [{"skill": skill, "jobs": count} for skill, count in counter.most_common(limit)]


def _rate(numerator: int, denominator: int) -> float:
    return round(100 * numerator / denominator, 1) if denominator else 0.0


def _mapping_lines(values: dict[str, int], empty: str) -> list[str]:
    if not values:
        return [empty]
    return [f"- **{key}:** {value}" for key, value in values.items()]
