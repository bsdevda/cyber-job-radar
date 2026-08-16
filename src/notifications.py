from __future__ import annotations

import hashlib
from typing import Any

from .scoring import recommendation


def build_job_alert(
    jobs: list[dict[str, Any]],
    config: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    """Build a deterministic, shell-safe GitHub Issue payload for new strong jobs."""
    options = config.get("notifications", {})
    enabled = bool(options.get("enabled", True))
    minimum_score = max(0, min(100, int(options.get("minimum_score", 80))))
    allowed_statuses = {
        str(value).upper() for value in options.get("new_statuses", ["NEW"])
    }
    maximum = max(1, int(options.get("maximum_jobs_per_alert", 10)))
    candidates = [
        job
        for job in jobs
        if str(job.get("status", "")).upper() in allowed_statuses
        and int(job.get("score", 0)) >= minimum_score
        and str(job.get("application_status", "NEW")).upper() == "NEW"
    ]
    candidates.sort(
        key=lambda job: (
            int(job.get("score", 0)),
            bool(job.get("priority_employer")),
            str(job.get("published_at") or ""),
        ),
        reverse=True,
    )
    selected = candidates[:maximum]
    digest_source = "\n".join(sorted(str(job.get("job_key")) for job in selected))
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()[:10]
    title = (
        f"[Job Radar] {len(selected)} new strong match"
        f"{'es' if len(selected) != 1 else ''} - {generated_at[:10]} [{digest}]"
    )
    compact_jobs = [_compact_alert_job(job) for job in selected]
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "enabled": enabled,
        "provider": str(options.get("provider") or "github_issue"),
        "minimum_score": minimum_score,
        "has_alert": enabled and bool(selected),
        "title": title,
        "deduplication_key": digest,
        "candidate_count": len(candidates),
        "included_count": len(selected),
        "truncated_count": max(0, len(candidates) - len(selected)),
        "jobs": compact_jobs,
    }


def render_job_alert_markdown(alert: dict[str, Any]) -> str:
    if not alert.get("has_alert"):
        return ""
    lines = [
        "# New high-priority cybersecurity vacancies",
        "",
        f"**Generated:** {alert.get('generated_at')}",
        f"**Alert threshold:** {alert.get('minimum_score')}/100",
        "",
        "> Automated evidence-based triage only. Open the original vacancy and verify every mandatory requirement before applying.",
        "",
    ]
    for index, job in enumerate(alert.get("jobs", []), 1):
        lines.extend(
            [
                f"## {index}. {_clean(job.get('title'))}",
                "",
                f"- **Company:** {_clean(job.get('company'))}",
                f"- **Location:** {_clean(job.get('location'))}",
                f"- **Score:** {job.get('score')}/100",
                f"- **Recommendation:** {_clean(job.get('recommendation'))}",
                f"- **Role family:** {_clean(job.get('role_family'))}",
                f"- **Posted:** {_clean(job.get('published_at') or 'Unknown')}",
                f"- **Vacancy:** [{_clean(job.get('company') or 'Open vacancy')}]({job.get('url')})",
                "",
                "**Why it matched:** " + (_clean(" ".join(job.get("match_reasons", []))) or "Review the structured score."),
                "",
                "**Risks to verify:** " + (_clean(" ".join(job.get("warnings", []))) or "No major automated warning."),
                "",
            ]
        )
    if alert.get("truncated_count"):
        lines.extend(
            [
                f"{alert['truncated_count']} additional strong match(es) are available in `reports/latest.json`.",
                "",
            ]
        )
    lines.extend(
        [
            "Upload `reports/chatgpt_handoff.json` to ChatGPT before tailoring the CV.",
            "",
            f"<!-- cyber-job-radar-alert:{alert.get('deduplication_key')} -->",
            "",
        ]
    )
    return "\n".join(lines)


def _compact_alert_job(job: dict[str, Any]) -> dict[str, Any]:
    role = job.get("role_family", {})
    return {
        "job_key": str(job.get("job_key") or ""),
        "title": str(job.get("title") or ""),
        "company": str(job.get("company") or ""),
        "location": str(job.get("location") or ""),
        "score": int(job.get("score", 0)),
        "recommendation": recommendation(int(job.get("score", 0))).split(" - ", 1)[0],
        "role_family": str(role.get("label") or "Other Security"),
        "published_at": str(job.get("published_at") or "")[:10],
        "url": str(job.get("apply_url") or job.get("url") or ""),
        "match_reasons": list(job.get("match_reasons", []))[:4],
        "warnings": list(job.get("warnings", []))[:5],
    }


def _clean(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("|", "\\|").strip()
