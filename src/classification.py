from __future__ import annotations

import re
from typing import Any

from .utils import normalize_text


SENIORITY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("executive", r"\b(?:chief|ciso|vice president|vp|director|head)\b"),
    ("manager", r"\b(?:manager|management)\b"),
    ("staff_principal", r"\b(?:staff\+?|principal|distinguished)\b"),
    ("lead", r"\b(?:lead|architect)\b"),
    ("senior", r"\b(?:senior|sr\.?|level\s*[4-9]|[ivx]{3,})\b"),
    ("junior", r"\b(?:junior|jr\.?|entry[ -]level|graduate|associate)\b"),
)

SENIORITY_LABELS = {
    "executive": "Executive",
    "manager": "Management",
    "staff_principal": "Staff/Principal",
    "lead": "Lead/Architect",
    "senior": "Senior",
    "junior": "Junior/Entry level",
    "mid_unspecified": "Mid-level or unspecified",
}


def classify_seniority(title: str) -> dict[str, str]:
    normalized = normalize_text(title)
    for level, pattern in SENIORITY_PATTERNS:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return {
                "level": level,
                "label": SENIORITY_LABELS[level],
                "evidence": match.group(0),
            }
    return {
        "level": "mid_unspecified",
        "label": SENIORITY_LABELS["mid_unspecified"],
        "evidence": "No explicit seniority marker in title",
    }


def classify_role(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    title = normalize_text(job.get("title", ""))
    description = normalize_text(job.get("description", ""))
    best: tuple[int, int, str, dict[str, Any], list[str]] | None = None

    for order, (family_id, family) in enumerate(config.get("role_families", {}).items()):
        title_hits = [term for term in family.get("title_terms", []) if normalize_text(term) in title]
        description_hits = [
            term for term in family.get("description_terms", []) if normalize_text(term) in description
        ]
        score = min(12, len(title_hits) * 6) + min(4, len(description_hits))
        if not score:
            continue
        candidate = (score, -order, family_id, family, title_hits + description_hits[:3])
        if best is None or candidate[:2] > best[:2]:
            best = candidate

    if best is None:
        return {
            "id": "other_security",
            "label": "Other Security",
            "priority": 3,
            "confidence": "low",
            "evidence": [],
        }

    score, _, family_id, family, evidence = best
    return {
        "id": family_id,
        "label": family.get("label", family_id.replace("_", " ").title()),
        "priority": int(family.get("priority", 3)),
        "confidence": "high" if score >= 6 else "medium",
        "evidence": evidence,
    }
