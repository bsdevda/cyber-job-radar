from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .classification import classify_seniority
from .eligibility import assess_location
from .utils import normalize_text


def hard_filter(job: dict[str, Any], config: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    title = normalize_text(job.get("title", ""))
    description = normalize_text(job.get("description", ""))
    location = normalize_text(job.get("location", ""))
    employment = normalize_text(job.get("employment_type", ""))

    seniority = job.get("seniority_analysis") or classify_seniority(job.get("title", ""))
    job["seniority_analysis"] = seniority
    if seniority.get("level") in {"executive", "manager", "staff_principal", "lead"}:
        reasons.append(f"Excluded seniority in title: {seniority.get('label')}")

    for term in config["hard_reject_title_terms"]:
        if term in title:
            reasons.append(f"Excluded seniority/employment type in title: {term}")
            break
    if any(term in employment for term in ("intern", "internship", "working student", "werkstudent")):
        reasons.append("Student/internship-only employment type")

    location_analysis = job.get("location_analysis") or assess_location(job, config)
    job["location_analysis"] = location_analysis
    if not location_analysis.get("eligible"):
        reasons.append(location_analysis.get("reason", "Location is outside the target region"))

    german = job.get("german_analysis", {})
    if german.get("mandatory") and german.get("category") in {
        "B2", "advanced", "C1", "C2", "native",
    }:
        reasons.append(german.get("label", "German proficiency is above the current profile"))

    posting_age = job.get("posting_age_analysis", {})
    age_days = posting_age.get("age_days")
    max_age = int(config.get("max_posting_age_days", 120))
    if age_days is not None and int(age_days) > max_age:
        reasons.append(f"Posting is too old: {age_days} days (maximum {max_age})")

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
    if any(term in title for term in config.get("hard_reject_non_cyber_title_terms", [])):
        return False
    all_roles = [role for roles in config["target_roles"].values() for role in roles]
    if any(role in title for role in all_roles):
        return True
    title_security_terms = (
        "security", "cyber", "appsec", "pentest", "penetration", "vulnerability",
        "soc analyst", "technology risk", "it audit", "devsecops",
    )
    if any(term in title for term in title_security_terms):
        return True
    # Description-only matches are deliberately insufficient. Generic cloud,
    # software, academic, sales, and physical-security jobs frequently mention
    # several cyber terms without being cybersecurity vacancies.
    return False


def summarize_rejections(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in rejected:
        for reason in item.get("rejection_reasons", []):
            counter[reason] += 1
    return dict(counter.most_common())
