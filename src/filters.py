from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .utils import normalize_text


def hard_filter(job: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    title = normalize_text(job.get("title", ""))
    description = normalize_text(job.get("description", ""))
    location = normalize_text(job.get("location", ""))
    employment = normalize_text(job.get("employment_type", ""))

    for term in config["hard_reject_title_terms"]:
        if term in title:
            reasons.append(f"Excluded seniority/employment type in title: {term}")
            break
    if any(term in employment for term in ("intern", "internship", "working student", "werkstudent")):
        reasons.append("Student/internship-only employment type")

    outside = config["outside_location_terms"]
    if any(term in location for term in outside):
        reasons.append("Location is explicitly outside Germany/Europe eligibility")
    outside_countries = {"united states", "usa", "canada", "united kingdom", "uk", "india", "australia"}
    if not job.get("remote") and job.get("country", "").casefold() in outside_countries:
        reasons.append("On-site role outside the target region")
    if not job.get("remote") and job.get("country") not in {"Germany", ""}:
        reasons.append("On-site role outside Germany")

    german = job.get("german_analysis", {})
    if german.get("mandatory") and german.get("category") in {"C1", "C2", "native"}:
        reasons.append(german.get("label", "German proficiency is above the current profile"))

    experience = job.get("experience_analysis")
    if experience and not experience.get("optional") and experience.get("min_years", 0) >= 8:
        reasons.append(f"Mandatory experience is too senior: {experience['display']}")

    citizenship_patterns = (
        r"\b(?:german|eu|european union) citizenship (?:is )?(?:required|mandatory)",
        r"\bmust (?:be|hold) (?:an? )?(?:german|eu) citizen",
        r"\bdeutsche staatsbürgerschaft (?:ist )?(?:erforderlich|zwingend)",
    )
    if any(re.search(pattern, description) for pattern in citizenship_patterns):
        reasons.append("Mandatory citizenship requirement")
    if re.search(r"\bactive (?:government|security) clearance (?:is )?(?:required|mandatory)\b", description):
        reasons.append("Active government/security clearance required")

    if not is_cybersecurity_relevant(job, config):
        reasons.append("Insufficient cybersecurity relevance")
    return not reasons, reasons


def is_cybersecurity_relevant(job: dict[str, Any], config: dict[str, Any]) -> bool:
    title = normalize_text(job.get("title", ""))
    description = normalize_text(job.get("description", ""))
    all_roles = [role for roles in config["target_roles"].values() for role in roles]
    if any(role in title for role in all_roles):
        return True
    title_security_terms = (
        "security", "cyber", "appsec", "pentest", "penetration", "vulnerability",
        "soc analyst", "technology risk", "it audit", "devsecops",
    )
    if any(term in title for term in title_security_terms):
        return True
    hits = {term for term in config["security_discovery_terms"] if term in description}
    return len(hits) >= 3


def summarize_rejections(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in rejected:
        for reason in item.get("rejection_reasons", []):
            counter[reason] += 1
    return dict(counter.most_common())
