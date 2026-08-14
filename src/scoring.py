from __future__ import annotations

from typing import Any

from .utils import normalize_text


SCORE_WEIGHTS = {
    "title": 20,
    "skills": 25,
    "experience": 15,
    "security_relevance": 10,
    "location": 10,
    "language": 10,
    "education": 5,
    "career_value": 5,
}


def score_job(job: dict[str, Any], config: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    breakdown = {
        "title": _title_score(job, config),
        "skills": _skills_score(job),
        "experience": _experience_score(job.get("experience_analysis")),
        "security_relevance": _security_relevance_score(job),
        "location": _location_score(job),
        "language": _language_score(job.get("german_analysis", {})),
        "education": _education_score(job),
        "career_value": _career_value_score(job),
    }
    score = max(0, min(100, sum(breakdown.values())))
    job["score"] = score
    job["score_breakdown"] = breakdown
    job["score_label"] = score_label(score)
    job["match_reasons"] = _match_reasons(job, breakdown)
    job["warnings"] = _warnings(job, profile)
    return job


def _title_score(job: dict[str, Any], config: dict[str, Any]) -> int:
    title = job.get("normalized_title") or normalize_text(job.get("title", ""))
    for tier, points in (("tier_1", 20), ("tier_2", 17), ("tier_3", 13)):
        if any(role in title or title in role for role in config["target_roles"][tier]):
            return points
    if any(term in title for term in ("security", "cyber", "vulnerability", "devsecops", "risk", "audit")):
        return 10
    return 6


def _skills_score(job: dict[str, Any]) -> int:
    categories = job.get("skill_matches", {})
    matched = len(categories.get("match", []))
    partial = len(categories.get("partial", []))
    missing = len(categories.get("missing", []))
    total = matched + partial + missing
    if total == 0:
        return 7
    ratio = (matched + 0.55 * partial) / total
    optional = categories.get("nice_to_have", [])
    optional_bonus = min(
        2.0,
        sum(0.3 if item.endswith("(match)") else 0.15 if item.endswith("(partial)") else 0 for item in optional),
    )
    return round(min(25, 5 + 18 * ratio + optional_bonus))


def _experience_score(experience: dict[str, Any] | None) -> int:
    if not experience:
        return 11
    years = int(experience.get("min_years", 0))
    if experience.get("optional"):
        years = max(0, years - 1)
    if years <= 2:
        return 15
    if years == 3:
        return 13
    if years == 4:
        return 10
    if years == 5:
        return 7
    if years <= 7:
        return 4
    return 0


def _security_relevance_score(job: dict[str, Any]) -> int:
    text = normalize_text(f"{job.get('title', '')} {job.get('description', '')}")
    appsec_terms = (
        "application security", "appsec", "product security", "api security", "web security",
        "mobile security", "penetration test", "sast", "dast", "secure sdlc", "threat model",
    )
    hits = sum(term in text for term in appsec_terms)
    if hits >= 4:
        return 10
    if hits >= 2:
        return 8
    if hits == 1:
        return 6
    return 4


def _location_score(job: dict[str, Any]) -> int:
    location = normalize_text(job.get("location", ""))
    if "berlin" in location:
        return 10
    if job.get("country") == "Germany":
        return 9
    if job.get("remote") and job.get("country") in {"Europe", "Worldwide"}:
        return 8
    if job.get("remote") and not job.get("country"):
        return 6
    return 2


def _language_score(german: dict[str, Any]) -> int:
    category = german.get("category", "none")
    if category == "none":
        return 10
    if category == "nice":
        return 9
    if category == "B1":
        return 7
    if category == "B2":
        return 3
    if category in {"C1", "C2", "native"}:
        return 1
    return 4


def _education_score(job: dict[str, Any]) -> int:
    text = normalize_text(job.get("description", ""))
    if any(term in text for term in ("master degree", "master's degree", "computer science", "cyber security", "cybersecurity degree")):
        return 5
    if any(term in text for term in ("bachelor", "university degree", "degree in")):
        return 5
    return 3


def _career_value_score(job: dict[str, Any]) -> int:
    text = normalize_text(f"{job.get('title', '')} {job.get('description', '')}")
    if any(term in text for term in ("application security", "appsec", "product security")):
        return 5
    growth = sum(term in text for term in ("api security", "sast", "dast", "secure sdlc", "threat model", "devsecops", "cloud security"))
    if growth >= 3:
        return 5
    if growth >= 1 or "security engineer" in text:
        return 4
    return 3


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
    if score >= 90:
        return "APPLY FIRST - verify the full vacancy and tailor the CV"
    if score >= 80:
        return "STRONG - REVIEW FOR APPLICATION"
    if score >= 70:
        return "GOOD - REVIEW REQUIREMENTS"
    if score >= 60:
        return "REVIEW - check gaps before applying"
    return "STRETCH - apply only if the role is strategically valuable"


def _match_reasons(job: dict[str, Any], breakdown: dict[str, int]) -> list[str]:
    reasons: list[str] = []
    if breakdown["title"] >= 17:
        reasons.append("The title is in a high-priority target role family.")
    if breakdown["security_relevance"] >= 8:
        reasons.append("The responsibilities align strongly with Application/Product Security work.")
    if breakdown["location"] >= 9:
        reasons.append("The role is based in Berlin/Germany.")
    if breakdown["language"] >= 9:
        reasons.append("No mandatory German level above the current profile was detected.")
    if job.get("skill_matches", {}).get("match"):
        skills = ", ".join(job["skill_matches"]["match"][:5])
        reasons.append(f"Strong evidenced skill matches include {skills}.")
    return reasons[:4]


def _warnings(job: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    german = job.get("german_analysis", {})
    if german.get("category") not in {"none", "nice"}:
        warnings.append(german.get("label", "Check the German-language requirement."))
    experience = job.get("experience_analysis")
    if experience and experience.get("min_years", 0) > float(profile.get("experience_years", 0)):
        warnings.append(f"Requests {experience['display']} versus approximately {profile.get('experience_years')} years in the profile.")
    missing = job.get("skill_matches", {}).get("missing", [])
    if missing:
        warnings.append("Potential skill gaps: " + ", ".join(missing[:6]))
    partial = job.get("skill_matches", {}).get("partial", [])
    if partial:
        warnings.append("Exposure only; do not claim deep expertise: " + ", ".join(partial[:6]))
    return warnings
