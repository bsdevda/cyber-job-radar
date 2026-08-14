from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

from .normalize import canonicalize_url, normalize_company, normalize_title
from .utils import normalize_text


AGGREGATOR_HOSTS = {"www.arbeitnow.com", "arbeitnow.com", "remotive.com", "www.remotive.com"}


def deduplicate_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    url_index: dict[str, int] = {}
    fingerprint_index: dict[str, int] = {}
    company_buckets: dict[str, list[int]] = defaultdict(list)

    for job in jobs:
        url = canonicalize_url(job.get("url", ""))
        fingerprint = _fingerprint(job)
        duplicate_index = url_index.get(url) if url else None
        if duplicate_index is None:
            duplicate_index = fingerprint_index.get(fingerprint)
        if duplicate_index is None:
            for candidate_index in company_buckets[normalize_company(job.get("company", ""))]:
                if _similar_job(deduped[candidate_index], job):
                    duplicate_index = candidate_index
                    break
        if duplicate_index is not None:
            deduped[duplicate_index] = _merge_jobs(deduped[duplicate_index], job)
            continue
        index = len(deduped)
        deduped.append(job)
        if url:
            url_index[url] = index
        fingerprint_index[fingerprint] = index
        company_buckets[normalize_company(job.get("company", ""))].append(index)
    return deduped


def _fingerprint(job: dict[str, Any]) -> str:
    return "|".join(
        (
            normalize_company(job.get("company", "")),
            normalize_title(job.get("title", "")),
            normalize_text(job.get("location", "")).replace("deutschland", "germany"),
        )
    )


def _similar_job(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = normalize_title(left.get("title", ""))
    right_title = normalize_title(right.get("title", ""))
    title_ratio = SequenceMatcher(None, left_title, right_title).ratio()
    if title_ratio < 0.9:
        return False
    left_location = normalize_text(left.get("location", ""))
    right_location = normalize_text(right.get("location", ""))
    if left_location != right_location and not (left.get("remote") and right.get("remote")):
        return False
    left_description = normalize_text(left.get("description", ""))[:5000]
    right_description = normalize_text(right.get("description", ""))[:5000]
    return SequenceMatcher(None, left_description, right_description).ratio() >= 0.88


def _merge_jobs(preferred: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(preferred)
    merged["sources"] = sorted(set(preferred.get("sources", [])) | set(incoming.get("sources", [])))
    merged["source_urls"] = {**preferred.get("source_urls", {}), **incoming.get("source_urls", {})}
    if len(incoming.get("description", "")) > len(preferred.get("description", "")):
        merged["description"] = incoming["description"]
    if _url_quality(incoming.get("url", "")) > _url_quality(preferred.get("url", "")):
        merged["url"] = incoming["url"]
        merged["source"] = incoming["source"]
        merged["source_id"] = incoming.get("source_id", "")
    merged["remote"] = bool(preferred.get("remote") or incoming.get("remote"))
    merged["hybrid"] = bool(preferred.get("hybrid") or incoming.get("hybrid"))
    merged["tags"] = sorted(set(preferred.get("tags", [])) | set(incoming.get("tags", [])))
    return merged


def _url_quality(url: str) -> int:
    host = urlsplit(url).netloc.casefold()
    if not host:
        return 0
    return 1 if host in AGGREGATOR_HOSTS else 3
