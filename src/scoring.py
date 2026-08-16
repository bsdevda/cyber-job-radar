from __future__ import annotations

from typing import Any

from .utils import normalize_text


SCORE_WEIGHTS = {
    "role_alignment": 20,
    "skills": 25,
    "experience": 15,
    "location": 15,
    "language": 10,
    "seniority": 10,
    "education": 5,
}


def score_job(job: dict[str, Any], config: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    breakdown = {
        "role_alignment": _role_alignment_score(job),
        "skills": _skills_score(job),
        "experience": _experience_score(job.get("experience_analysis")),
        "location": int(job.get("location_analysis", {}).get("score", 0)),
        "language": _language_score(job.get("german_analysis", {})),
        "seniority": _seniority_score(job.get("seniority_analysis", {})),
        "education": _education_score(job),
    }
    raw_score = max(0, min(100, sum(breakdown.values())))
    caps = _score_caps(job, config)
    cap = min((item["cap"] for item in caps), default=100)
    score = min(raw_score, cap)

    job["raw_score"] = raw_score
    job["score"] = score
    job["score_cap"] = cap if cap < 100 else None
    job["score_cap_reasons"] = [item["reason"] for item in caps if item["cap"] == cap]
    job["score_breakdown"] = breakdown
    job["score_label"] = score_label(score)
    job["match_reasons"] = _match_reasons(job, breakdown)
    job["warnings"] = _warnings(job, profile)
    return job


def _role_alignment_score(job: dict[str, Any]) -> int:
    role = job.get("role_family", {})
    priority = int(role.get("priority", 3))
    confidence = role.get("confidence", "low")
    base = {1: 20, 2: 16, 3: 12}.get(priority, 10)
    return max(8, base - (2 if confidence == "low" else 0))


def _skills_score(job: dict[str, Any]) -> int:
    requirements = [
        item for item in job.get("skill_requirements", []) if item.get("requirement") != "optional"
    ]
    if requirements:
        values = {"match": 1.0, "partial": 0.5, "missing": 0.0}
        ratio = sum(values.get(item.get("profile_status", "missing"), 0.0) for item in requirements)
        ratio /= len(requirements)
        optional_bonus = min(
            2.0,
            sum(
                0.35 if item.get("profile_status") == "match" else 0.15
                for item in job.get("skill_requirements", [])
                if item.get("requirement") == "optional"
            ),
        )
        return round(min(25, 4 + 19 * ratio + optional_bonus))

    categories = job.get("skill_matches", {})
    matched = len(categories.get("match", []))
    partial = len(categories.get("partial", []))
    missing = len(categories.get("missing", []))
    total = matched + partial + missing
    if total == 0:
        return 5
    return round(min(25, 4 + 19 * ((matched + 0.5 * partial) / total)))


def _experience_score(experience: dict[str, Any] | None) -> int:
    if not experience:
        return 10
    years = int(experience.get("min_years", 0))
    if experience.get("optional"):
        years = max(0, years - 1)
    if years <= 2:
        return 15
    if years == 3:
        return 12
    if years == 4:
        return 8
    if years == 5:
        return 4
    return 0


def _language_score(german: dict[str, Any]) -> int:
    category = german.get("category", "none")
    if category == "none":
        return 10
    if category == "nice":
        return 9
    if category in {"A1", "A2"}:
        return 8
    if category == "B1":
        return 6
    if category == "B2":
        return 1
    if category in {"advanced", "C1", "C2", "native"}:
        return 0
    if category == "required":
        return 2
    return 4


def _seniority_score(seniority: dict[str, Any]) -> int:
    return {
        "junior": 10,
        "mid_unspecified": 10,
        "senior": 4,
        "lead": 0,
        "staff_principal": 0,
        "manager": 0,
        "executive": 0,
    }.get(seniority.get("level", "mid_unspecified"), 7)


def _education_score(job: dict[str, Any]) -> int:
    text = normalize_text(job.get("description", ""))
    if any(
        term in text
        for term in (
            "master degree", "master's degree", "computer science", "cyber security",
            "cybersecurity degree", "bachelor", "university degree", "degree in",
        )
    ):
        return 5
    return 3


def _score_caps(job: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    caps: list[dict[str, Any]] = []
    if job.get("lead_type") == "linkedin_post":
        caps.append(
            {
                "cap": 69,
                "reason": "LinkedIn post lead: verify the complete official vacancy before applying",
            }
        )
    location_cap = job.get("location_analysis", {}).get("score_cap")
    if location_cap:
        caps.append({"cap": int(location_cap), "reason": job["location_analysis"]["reason"]})

    seniority = job.get("seniority_analysis", {}).get("level")
    if seniority == "senior":
        caps.append({"cap": 69, "reason": "Senior title is above the profile's current 2+ years"})

    experience = job.get("experience_analysis")
    if experience and not experience.get("optional"):
        years = int(experience.get("min_years", 0))
        if years >= 5:
            caps.append({"cap": 59, "reason": f"Mandatory experience requirement is {experience['display']}"})
        elif years == 4:
            caps.append({"cap": 69, "reason": f"Mandatory experience requirement is {experience['display']}"})
        elif years == 3:
            caps.append({"cap": 79, "reason": f"Mandatory experience requirement is {experience['display']}"})

    german = job.get("german_analysis", {})
    if german.get("mandatory") and german.get("category") == "B1":
        caps.append({"cap": 69, "reason": "German B1 is mandatory while the profile is currently A2"})
    elif german.get("mandatory") and german.get("category") == "required":
        caps.append({"cap": 59, "reason": "German is mandatory but the required level is not stated"})

    mandatory_gaps = job.get("mandatory_gaps", [])
    missing_mandatory = sum(
        item.get("profile_status") == "missing" for item in mandatory_gaps
    )
    if missing_mandatory >= 2:
        caps.append({"cap": 59, "reason": "Multiple explicitly mandatory skills are not evidenced"})
    elif missing_mandatory == 1:
        caps.append({"cap": 69, "reason": "One explicitly mandatory skill is not evidenced"})
    elif mandatory_gaps:
        caps.append({"cap": 69, "reason": "At least one explicitly mandatory skill has exposure only"})

    posting_age = job.get("posting_age_analysis", {})
    age_days = posting_age.get("age_days")
    if age_days is None:
        caps.append({"cap": 79, "reason": "Posting date is unknown; verify that the vacancy is active"})
    elif int(age_days) > int(config.get("stale_posting_score_cap_days", 60)):
        caps.append({"cap": 69, "reason": f"Posting is {age_days} days old; verify that it is active"})
    return caps


def score_label(score: int) -> str:
    if score >= 90:
        return "EXCELLENT"
    if score >= 80:
        return "STRONG"
    if score >= 70:
        return "GOOD"
    if score >= 60:
        return "REVIEW"
    if score >= 50:
        return "STRETCH"
    return "LOW PRIORITY"


def recommendation(score: int) -> str:
    if score >= 85:
        return "APPLY FIRST - verify the full vacancy and tailor the CV"
    if score >= 80:
        return "APPLY - strong evidence-based match"
    if score >= 70:
        return "REVIEW - verify mandatory requirements before applying"
    if score >= 60:
        return "REVIEW - material seniority, language, or skill risk"
    return "STRETCH - apply only after manually resolving the flagged risks"


def _match_reasons(job: dict[str, Any], breakdown: dict[str, int]) -> list[str]:
    reasons: list[str] = []
    role = job.get("role_family", {})
    if breakdown["role_alignment"] >= 16:
        reasons.append(f"Role family: {role.get('label', 'target security role')}.")
    location = job.get("location_analysis", {})
    if location.get("category") == "eligible_germany":
        reasons.append("The role is based in Berlin/Germany or explicitly accepts Germany.")
    elif location.get("eligible"):
        reasons.append(location.get("reason", "Remote eligibility detected.") + ".")
    matches = job.get("skill_matches", {}).get("match", [])
    if matches:
        reasons.append("Evidenced matches include " + ", ".join(matches[:5]) + ".")
    if breakdown["experience"] >= 12:
        reasons.append("The detected experience requirement is within or close to the 2+ year profile.")
    return reasons[:4]


def _warnings(job: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    location = job.get("location_analysis", {})
    if location.get("verification_required"):
        warnings.append(location.get("reason", "Verify location eligibility."))
    german = job.get("german_analysis", {})
    if german.get("category") not in {"none", "nice"}:
        warnings.append(german.get("label", "Check the German-language requirement."))
    experience = job.get("experience_analysis")
    if experience and experience.get("min_years", 0) > float(profile.get("experience_years", 0)):
        warnings.append(
            f"Requests {experience['display']} versus approximately {profile.get('experience_years')} years in the profile."
        )
    for label, key in (
        ("Mandatory gaps", "mandatory_gaps"),
        ("Potential gaps", "potential_gaps"),
        ("Optional gaps", "optional_gaps"),
    ):
        values = [item.get("skill", "") for item in job.get(key, [])]
        if values:
            warnings.append(f"{label}: " + ", ".join(values[:6]))
    partial = job.get("skill_matches", {}).get("partial", [])
    if partial:
        warnings.append("Exposure only; do not claim deep expertise: " + ", ".join(partial[:6]))
    warnings.extend(job.get("score_cap_reasons", []))
    return list(dict.fromkeys(warnings))
