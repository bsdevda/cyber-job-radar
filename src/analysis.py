from __future__ import annotations

import re
from typing import Any

from .utils import normalize_text


OPTIONAL_MARKERS = (
    "nice to have", "preferred", "preferably", "a plus", "bonus", "advantageous",
    "beneficial", "desirable", "optional", "von vorteil", "wünschenswert",
)
MANDATORY_MARKERS = (
    "required", "must", "mandatory", "minimum", "at least", "proficiency",
    "fluent", "excellent", "business fluent", "zwingend", "voraussetzung",
    "mindestens", "verhandlungssicher", "sehr gute", "fließend",
)


def sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|[\r\n]+|[•●▪]", text) if part.strip()]


def is_optional_context(text: str) -> bool:
    lowered = normalize_text(text)
    return any(marker in lowered for marker in OPTIONAL_MARKERS)


def detect_german_requirement(description: str) -> dict[str, Any]:
    candidates = [
        sentence for sentence in sentences(description)
        if re.search(r"\b(german|deutsch(?:e|en|er|es)?|deutschkenntnisse)\b", normalize_text(sentence))
    ]
    best: dict[str, Any] | None = None
    rank = {"none": 0, "nice": 1, "unspecified": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6, "native": 7}
    for sentence in candidates:
        lowered = normalize_text(sentence)
        optional = is_optional_context(lowered)
        mandatory = any(marker in lowered for marker in MANDATORY_MARKERS) and not optional
        if re.search(r"\b(native|muttersprach(?:e|lich))\b", lowered):
            level = "native"
        else:
            match = re.search(r"\b([abc][12])\b", lowered, flags=re.IGNORECASE)
            level = match.group(1).upper() if match else "unspecified"
        if optional:
            category = "nice"
            label = f"German {level} is preferred/nice-to-have" if level != "unspecified" else "German is preferred/nice-to-have"
        elif mandatory or level in {"B1", "B2", "C1", "C2", "native"}:
            category = level
            label = f"German {level} required" if level != "native" else "Native German required"
        else:
            category = "unspecified"
            label = "German requested; level/strictness unclear"
        item = {"category": category, "level": level, "mandatory": not optional and category != "unspecified", "label": label, "evidence": sentence[:240]}
        if best is None or rank[category] > rank[best["category"]]:
            best = item
    if best:
        return best
    if looks_mostly_german(description):
        return {
            "category": "unspecified",
            "level": "unspecified",
            "mandatory": False,
            "label": "Working language appears German (level not stated)",
            "evidence": "The vacancy text is predominantly German.",
        }
    return {"category": "none", "level": "none", "mandatory": False, "label": "No German requirement detected", "evidence": ""}


def looks_mostly_german(text: str) -> bool:
    lowered = f" {normalize_text(text[:8000])} "
    if len(lowered) < 300:
        return False
    markers = (
        " und ", " oder ", " wir ", " du ", " sie ", " deine ", " ihre ",
        " erfahrung ", " kenntnisse ", " aufgaben ", " bewerbung ", " sicherheit ",
        " verantwortlich ", " gemeinsam ", " unserem ", " unserer ",
    )
    return sum(lowered.count(marker) for marker in markers) >= 9


def extract_experience(description: str) -> dict[str, Any] | None:
    relevant: list[tuple[int, int | None, bool, str]] = []
    year_pattern = re.compile(r"\b(\d{1,2})(?:\s*[-–—]\s*(\d{1,2}))?\s*\+?\s*(?:years?|yrs?|jahre?n?)\b", re.IGNORECASE)
    context_pattern = re.compile(r"\b(experience|experienced|background|berufserfahrung|erfahrung)\b", re.IGNORECASE)
    for sentence in sentences(description):
        if not context_pattern.search(sentence):
            continue
        for match in year_pattern.finditer(sentence):
            minimum = int(match.group(1))
            maximum = int(match.group(2)) if match.group(2) else None
            if minimum > 20 or (maximum and maximum > 30):
                continue
            relevant.append((minimum, maximum, is_optional_context(sentence), sentence[:260]))
    if not relevant:
        return None
    mandatory_items = [item for item in relevant if not item[2]]
    selected = max(mandatory_items or relevant, key=lambda item: item[0])
    minimum, maximum, optional, evidence = selected
    display = f"{minimum}-{maximum} years" if maximum else f"{minimum}+ years"
    if optional:
        display += " preferred"
    return {"min_years": minimum, "max_years": maximum, "optional": optional, "display": display, "evidence": evidence}


def detect_skills(
    description: str,
    aliases: dict[str, list[str]],
    profile_status: dict[str, str],
) -> tuple[list[str], dict[str, list[str]]]:
    text_sentences = sentences(description)
    normalized_sentences = [normalize_text(sentence) for sentence in text_sentences]
    categories: dict[str, list[str]] = {"match": [], "partial": [], "missing": [], "nice_to_have": []}
    detected: list[str] = []
    for skill, variants in aliases.items():
        occurrences: list[bool] = []
        for sentence in normalized_sentences:
            if any(_contains_alias(sentence, alias) for alias in variants):
                occurrences.append(is_optional_context(sentence))
        if not occurrences:
            continue
        detected.append(skill)
        status = profile_status.get(skill, "missing")
        if all(occurrences):
            categories["nice_to_have"].append(f"{skill} ({status})")
        else:
            categories[status if status in {"match", "partial", "missing"} else "missing"].append(skill)
    for values in categories.values():
        values.sort()
    return sorted(detected), categories


def _contains_alias(sentence: str, alias: str) -> bool:
    needle = normalize_text(alias)
    if len(needle) <= 3 and needle.isalnum():
        return bool(re.search(rf"\b{re.escape(needle)}\b", sentence))
    return needle in sentence
