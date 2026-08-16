from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .utils import normalize_text


OPTIONAL_MARKERS = (
    "nice to have", "nice-to-have", "preferred", "preferably", "a plus", "bonus", "advantageous",
    "beneficial", "desirable", "optional", "von vorteil", "wünschenswert",
)
MANDATORY_MARKERS = (
    "required", "must", "mandatory", "minimum", "at least", "proficiency",
    "fluency", "fluent", "excellent", "very good", "business fluent",
    "professional proficiency", "working language", "zwingend", "voraussetzung",
    "mindestens", "verhandlungssicher", "sehr gute", "fließend",
)
ADVANCED_LANGUAGE_MARKERS = (
    "fluency", "fluent", "excellent", "very good", "business fluent",
    "professional proficiency", "verhandlungssicher", "sehr gute", "fließend",
)
SKILL_REQUIREMENT_MARKERS = MANDATORY_MARKERS + (
    "proven experience", "hands-on experience", "strong experience", "expertise in",
    "strong knowledge", "solid knowledge", "practical knowledge", "familiarity with",
    "knowledge of", "experience with", "experience in", "several years", "you have",
    "you bring", "you can", "comfortable with", "proficient in", "advanced skills",
    "mehrjährige", "fundierte", "fortgeschrittene", "ausgeprägt", "du hast",
    "du bringst", "verfügst über", "erfahrung mit", "erfahrung in", "kenntnisse in",
)


def sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+|;\s+|[\r\n]+|[•●▪]", text)
        if part.strip()
    ]


def is_optional_context(text: str) -> bool:
    lowered = normalize_text(text)
    return any(marker in lowered for marker in OPTIONAL_MARKERS)


def sentence_contexts(text: str) -> list[tuple[str, bool]]:
    """Return sentences with optional-section state propagated from nearby headings."""
    optional_section = False
    result: list[tuple[str, bool]] = []
    optional_headings = (
        "nice to have", "nice-to-have", "preferred qualifications",
        "optional qualifications", "bonus qualifications", "wünschenswert",
        "von vorteil",
    )
    reset_headings = (
        "what you will need", "who you are", "requirements", "qualifications",
        "your profile", "dein profil", "womit du überzeugst", "must have",
        "what you will do", "responsibilities", "aufgaben", "deine aufgaben",
        "what we offer", "benefits", "warum zu uns",
    )
    for sentence in sentences(text):
        normalized = normalize_text(sentence).strip(" :-")
        if len(normalized) <= 80 and any(
            normalized == heading or normalized.startswith(heading + " ")
            for heading in optional_headings
        ):
            optional_section = True
            result.append((sentence, True))
            continue
        if len(normalized) <= 80 and any(
            normalized == heading or normalized.startswith(heading + " ")
            for heading in reset_headings
        ):
            optional_section = False
            result.append((sentence, False))
            continue
        result.append((sentence, optional_section))
    return result


def detect_german_requirement(description: str) -> dict[str, Any]:
    candidates = [
        sentence for sentence in sentences(description)
        if _contains_german_language_reference(sentence)
    ]
    best: dict[str, Any] | None = None
    rank = {
        "none": 0,
        "nice": 1,
        "unspecified": 2,
        "A1": 3,
        "A2": 4,
        "B1": 5,
        "required": 6,
        "B2": 7,
        "advanced": 8,
        "C1": 9,
        "C2": 10,
        "native": 11,
    }
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
        elif level in {"A1", "A2", "B1", "B2", "C1", "C2", "native"}:
            category = level
            label = f"German {level} required" if level != "native" else "Native German required"
        elif any(marker in lowered for marker in ADVANCED_LANGUAGE_MARKERS):
            category = "advanced"
            level = "advanced"
            label = "Advanced/fluent German required"
        elif mandatory:
            category = "required"
            label = "German proficiency required (level not stated)"
        else:
            category = "unspecified"
            label = "German requested; level/strictness unclear"
        item = {
            "category": category,
            "level": level,
            "mandatory": not optional and category not in {"unspecified", "nice"},
            "label": label,
            "evidence": sentence[:240],
        }
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


def _contains_german_language_reference(sentence: str) -> bool:
    """Detect language requirements without treating German company names as language evidence."""
    lowered = normalize_text(sentence)
    if re.search(r"\bgerman\b", lowered):
        return True
    if re.search(r"\bdeutsch(?:kenntnisse|sprachig|sprache)\b", lowered):
        return True
    if re.search(r"\bdeutsche\s+(?:sprache|sprachkenntnisse)\b", lowered):
        return True
    return bool(re.search(r"\b(?:auf\s+)?deutsch\b", lowered))


def analyze_posting_age(published_at: str, reference_at: str) -> dict[str, Any]:
    """Return deterministic posting-age evidence for filtering, scoring, and reports."""
    try:
        published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        reference = datetime.fromisoformat(str(reference_at).replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=UTC)
        age_days = max(0, (reference - published).days)
    except (ValueError, TypeError, AttributeError):
        return {
            "known": False,
            "age_days": None,
            "category": "unknown",
            "label": "POSTING DATE UNKNOWN",
        }
    if age_days <= 2:
        category, label = "new", "NEW - APPLY QUICKLY"
    elif age_days <= 7:
        category, label = "recent", "RECENT"
    elif age_days <= 30:
        category, label = "current", "OPEN FOR REVIEW"
    else:
        category, label = "older", "OLDER POSTING - VERIFY ACTIVE"
    return {
        "known": True,
        "age_days": age_days,
        "category": category,
        "label": label,
    }


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
    contextual_sentences = sentence_contexts(description)
    categories: dict[str, list[str]] = {"match": [], "partial": [], "missing": [], "nice_to_have": []}
    detected: list[str] = []
    for skill, variants in aliases.items():
        occurrences: list[bool] = []
        for raw_sentence, optional_section in contextual_sentences:
            sentence = normalize_text(raw_sentence)
            if any(_contains_alias(sentence, alias) for alias in variants):
                occurrences.append(optional_section or is_optional_context(sentence))
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


def analyze_skill_requirements(
    description: str,
    aliases: dict[str, list[str]],
    profile_status: dict[str, str],
) -> list[dict[str, Any]]:
    """Return requirement strength and short evidence for every detected skill."""
    results: list[dict[str, Any]] = []
    for skill, variants in aliases.items():
        matches: list[tuple[str, str]] = []
        for sentence, optional_section in sentence_contexts(description):
            normalized = normalize_text(sentence)
            if not any(_contains_alias(normalized, alias) for alias in variants):
                continue
            if optional_section or is_optional_context(normalized):
                requirement = "optional"
            elif any(marker in normalized for marker in SKILL_REQUIREMENT_MARKERS):
                requirement = "mandatory"
            else:
                requirement = "mentioned"
            matches.append((requirement, sentence[:260]))
        if not matches:
            continue
        strengths = {"mentioned": 1, "optional": 2, "mandatory": 3}
        requirement, evidence = max(matches, key=lambda item: strengths[item[0]])
        results.append(
            {
                "skill": skill,
                "profile_status": profile_status.get(skill, "missing"),
                "requirement": requirement,
                "evidence": evidence,
            }
        )
    return sorted(results, key=lambda item: (item["requirement"], item["skill"]))


def _contains_alias(sentence: str, alias: str) -> bool:
    needle = normalize_text(alias)
    if len(needle) <= 3 and needle.isalnum():
        return bool(re.search(rf"\b{re.escape(needle)}\b", sentence))
    return needle in sentence
