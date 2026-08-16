from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .utils import html_to_text, normalize_text


GERMAN_CITIES = {
    "berlin", "hamburg", "munich", "münchen", "cologne", "köln", "frankfurt",
    "stuttgart", "düsseldorf", "dusseldorf", "leipzig", "dresden", "potsdam",
    "nuremberg", "nürnberg", "bonn", "bremen", "hanover", "hannover",
}


def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_")
            and key.casefold() not in {"source", "ref", "referrer", "gh_src"}
        ]
        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
        return urlunsplit((parts.scheme.casefold(), parts.netloc.casefold(), path, urlencode(query), ""))
    except ValueError:
        return url.strip()


def normalize_title(title: str) -> str:
    value = normalize_text(title)
    value = re.sub(
        r"\((?:m/f/d|f/m/d|m/w/d|w/m/d|all genders|gn|any gender|x/f/m|m/f/x)\)",
        " ",
        value,
    )
    value = re.sub(r"\b(?:m/f/d|f/m/d|m/w/d|all genders)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip(" -/")


def normalize_company(company: str) -> str:
    value = normalize_text(company)
    value = re.sub(r"\b(gmbh|ag|se|ltd|limited|inc|corp|corporation|ug)\b\.?", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_location(location: str, remote_flag: bool, description: str = "") -> tuple[str, str, bool, bool]:
    raw = html_to_text(location).strip() or ("Remote" if remote_flag else "Unspecified")
    lowered = normalize_text(raw)
    description_lower = normalize_text(description[:3000])
    remote = remote_flag or bool(re.search(r"\b(remote|home office|work from home)\b", lowered))
    hybrid = "hybrid" in lowered or "hybrid" in description_lower

    if "berlin" in lowered:
        return "Berlin, Germany", "Germany", remote, hybrid
    if "germany" in lowered or "deutschland" in lowered or any(city in lowered for city in GERMAN_CITIES):
        cleaned = re.sub(r"\bdeutschland\b", "Germany", raw, flags=re.IGNORECASE)
        if "germany" not in cleaned.casefold():
            cleaned = f"{cleaned}, Germany"
        return cleaned, "Germany", remote, hybrid
    if any(term in lowered for term in ("europe", "european union", "eu remote", "emea")):
        return raw, "Europe", True, hybrid
    if "worldwide" in lowered or "anywhere" in lowered or "global" in lowered:
        return raw, "Worldwide", True, hybrid
    country = ""
    for candidate in ("united states", "usa", "canada", "united kingdom", "uk", "india", "australia"):
        if re.search(rf"\b{re.escape(candidate)}\b", lowered):
            country = candidate.title()
            break
    return raw, country, remote, hybrid


def normalize_datetime(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().replace(" ", "T", 1) if " " in value and "T" not in value else value.strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return value.strip()


def job_key_for(company: str, title: str, location: str) -> str:
    location_key = normalize_text(location).replace("deutschland", "germany")
    payload = "|".join((normalize_company(company), normalize_title(title), location_key))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def content_hash(job: dict[str, Any]) -> str:
    fields = [
        job.get("title", ""), job.get("company", ""), job.get("location", ""),
        job.get("description", ""), job.get("salary", ""), job.get("employment_type", ""),
    ]
    return hashlib.sha256("|".join(map(str, fields)).encode("utf-8")).hexdigest()


def normalize_job(raw: dict[str, Any]) -> dict[str, Any]:
    description = html_to_text(str(raw.get("description") or ""))
    location, country, remote, hybrid = normalize_location(
        str(raw.get("location") or ""), bool(raw.get("remote")), description
    )
    hybrid = bool(raw.get("hybrid")) or hybrid
    source = str(raw.get("source") or "Unknown")
    company = html_to_text(str(raw.get("company") or "Unknown company"))
    title = html_to_text(str(raw.get("title") or "Untitled role"))
    url = canonicalize_url(str(raw.get("url") or ""))
    apply_url = canonicalize_url(str(raw.get("apply_url") or url))
    canonical_url = canonicalize_url(str(raw.get("canonical_url") or url))
    source_job_id = str(raw.get("source_job_id") or raw.get("source_id") or "")
    title_normalized = normalize_title(title)
    job = {
        "job_key": job_key_for(company, title, location),
        "source": source,
        "sources": [source],
        "source_urls": {source: url},
        "source_id": source_job_id,
        "source_job_id": source_job_id,
        "source_job_ids": {source: source_job_id} if source_job_id else {},
        "company": company,
        "company_normalized": normalize_company(company),
        "title": title,
        "normalized_title": title_normalized,
        "title_normalized": title_normalized,
        "location": location,
        "location_normalized": normalize_text(location).replace("deutschland", "germany"),
        "country": country,
        "remote": remote,
        "hybrid": hybrid,
        "onsite": not remote and not hybrid,
        "url": url,
        "apply_url": apply_url,
        "canonical_url": canonical_url,
        "ats": normalize_text(str(raw.get("ats") or "")),
        "published_at": normalize_datetime(str(raw.get("published_at") or "")),
        "first_seen": "",
        "last_seen": "",
        "description": description,
        "salary": html_to_text(str(raw.get("salary") or "")),
        "employment_type": html_to_text(str(raw.get("employment_type") or "")),
        "experience_required": None,
        "german_requirement": "Not detected",
        "skills_detected": [],
        "skill_matches": {"match": [], "partial": [], "missing": [], "nice_to_have": []},
        "score": 0,
        "score_label": "LOW PRIORITY",
        "score_breakdown": {},
        "match_reasons": [],
        "warnings": [],
        "status": "NEW",
        "priority_employer": False,
        "tags": sorted({html_to_text(str(tag)) for tag in raw.get("tags", []) if tag}),
        "lead_type": str(raw.get("lead_type") or ""),
        "post_author": html_to_text(str(raw.get("post_author") or "")),
        "feed_name": html_to_text(str(raw.get("feed_name") or "")),
    }
    job["content_hash"] = content_hash(job)
    return job
