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
    source_id_index: dict[str, int] = {}
    fingerprint_index: dict[str, int] = {}
    company_buckets: dict[str, list[int]] = defaultdict(list)

    for job in jobs:
        urls = _job_urls(job)
        source_id_key = _source_id_key(job)
        fingerprint = _fingerprint(job)
        duplicate_index = next((url_index[url] for url in urls if url in url_index), None)
        if duplicate_index is None and source_id_key:
            duplicate_index = source_id_index.get(source_id_key)
        if duplicate_index is None:
            duplicate_index = fingerprint_index.get(fingerprint)
        if duplicate_index is None:
            for candidate_index in company_buckets[normalize_company(job.get("company", ""))]:
                if _similar_job(deduped[candidate_index], job):
                    duplicate_index = candidate_index
                    break
        if duplicate_index is not None:
            deduped[duplicate_index] = _merge_jobs(deduped[duplicate_index], job)
            for merged_url in _job_urls(deduped[duplicate_index]):
                url_index[merged_url] = duplicate_index
            merged_source_id = _source_id_key(deduped[duplicate_index])
            if merged_source_id:
                source_id_index[merged_source_id] = duplicate_index
            for source, source_job_id in deduped[duplicate_index].get("source_job_ids", {}).items():
                if source_job_id:
                    source_id_index[f"{source.casefold()}|{source_job_id}"] = duplicate_index
            continue
        index = len(deduped)
        deduped.append(job)
        for url in urls:
            url_index[url] = index
        if source_id_key:
            source_id_index[source_id_key] = index
        fingerprint_index[fingerprint] = index
        company_buckets[normalize_company(job.get("company", ""))].append(index)
    return deduped


def _job_urls(job: dict[str, Any]) -> set[str]:
    candidates = [
        job.get("url", ""),
        job.get("apply_url", ""),
        job.get("canonical_url", ""),
        *job.get("source_urls", {}).values(),
    ]
    return {canonicalize_url(str(url)) for url in candidates if url}


def _source_id_key(job: dict[str, Any]) -> str:
    source_job_id = str(job.get("source_job_id") or job.get("source_id") or "")
    if not source_job_id:
        return ""
    namespace = str(job.get("ats") or job.get("source") or "").casefold()
    return f"{namespace}|{source_job_id}"


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
    merged["source_job_ids"] = {
        **preferred.get("source_job_ids", {}),
        **incoming.get("source_job_ids", {}),
    }
    if len(incoming.get("description", "")) > len(preferred.get("description", "")):
        merged["description"] = incoming["description"]
    if _source_quality(incoming) > _source_quality(preferred):
        for field in (
            "url", "apply_url", "canonical_url", "ats", "source_id", "source_job_id",
        ):
            merged[field] = incoming.get(field, "")
        merged["source"] = incoming["source"]
    merged["remote"] = bool(preferred.get("remote") or incoming.get("remote"))
    merged["hybrid"] = bool(preferred.get("hybrid") or incoming.get("hybrid"))
    merged["onsite"] = not merged["remote"] and not merged["hybrid"]
    merged["tags"] = sorted(set(preferred.get("tags", [])) | set(incoming.get("tags", [])))
    return merged


def _source_quality(job: dict[str, Any]) -> int:
    url = job.get("canonical_url") or job.get("apply_url") or job.get("url", "")
    if job.get("ats") and url:
        return 4
    return _url_quality(url)


def _url_quality(url: str) -> int:
    host = urlsplit(url).netloc.casefold()
    if not host:
        return 0
    return 1 if host in AGGREGATOR_HOSTS else 3
