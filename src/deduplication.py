from __future__ import annotations

import hashlib
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlsplit

from .normalize import canonicalize_url, normalize_company, normalize_title
from .utils import normalize_text


AGGREGATOR_HOSTS = {"www.arbeitnow.com", "arbeitnow.com", "remotive.com", "www.remotive.com"}


def deduplicate_jobs(
    jobs: list[dict[str, Any]], config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    config = config or {}
    min_description_chars = int(config.get("duplicate_description_min_chars", 500))
    anchor_candidate_limit = max(1, int(config.get("duplicate_anchor_candidate_limit", 20)))
    company_candidate_limit = max(1, int(config.get("duplicate_company_candidate_limit", 100)))
    deduped: list[dict[str, Any]] = []
    url_index: dict[str, int] = {}
    source_id_index: dict[str, int] = {}
    fingerprint_index: dict[str, int] = {}
    description_index: dict[str, int] = {}
    description_anchor_buckets: dict[str, list[int]] = defaultdict(list)
    company_buckets: dict[str, list[int]] = defaultdict(list)

    for job in jobs:
        urls = _job_urls(job)
        source_id_key = _source_id_key(job)
        fingerprint = _fingerprint(job)
        description_fingerprint = _description_fingerprint(job, min_description_chars)
        description_anchor = _description_anchor(job, min_description_chars)
        duplicate_index = next((url_index[url] for url in urls if url in url_index), None)
        if duplicate_index is None and source_id_key:
            duplicate_index = source_id_index.get(source_id_key)
        if duplicate_index is None:
            duplicate_index = fingerprint_index.get(fingerprint)
        if duplicate_index is None and description_fingerprint:
            duplicate_index = description_index.get(description_fingerprint)
        if duplicate_index is None and description_anchor:
            for candidate_index in description_anchor_buckets[description_anchor][
                -anchor_candidate_limit:
            ]:
                if _descriptions_near_duplicate(deduped[candidate_index], job, config):
                    duplicate_index = candidate_index
                    break
        if duplicate_index is None:
            for candidate_index in company_buckets[normalize_company(job.get("company", ""))][
                -company_candidate_limit:
            ]:
                if _similar_job(deduped[candidate_index], job, config):
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
            merged_description_fingerprint = _description_fingerprint(
                deduped[duplicate_index], min_description_chars
            )
            if merged_description_fingerprint:
                description_index[merged_description_fingerprint] = duplicate_index
            continue
        index = len(deduped)
        deduped.append(job)
        for url in urls:
            url_index[url] = index
        if source_id_key:
            source_id_index[source_id_key] = index
        fingerprint_index[fingerprint] = index
        if description_fingerprint:
            description_index[description_fingerprint] = index
        if description_anchor:
            description_anchor_buckets[description_anchor].append(index)
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


def _description_fingerprint(job: dict[str, Any], min_chars: int) -> str:
    company = normalize_company(job.get("company", ""))
    description = normalize_text(job.get("description", ""))
    if not company or len(description) < min_chars:
        return ""
    digest = hashlib.sha256(description.encode("utf-8")).hexdigest()
    return f"{company}|{digest}"


def _description_anchor(job: dict[str, Any], min_chars: int) -> str:
    company = normalize_company(job.get("company", ""))
    description = normalize_text(job.get("description", ""))
    if not company or len(description) < min_chars:
        return ""
    # Employer boards commonly vary only a benefit, location, or tracking line.
    # Company + coarse length + stable opening text creates a small candidate
    # bucket; the full description ratio below still decides the duplicate.
    length_bucket = len(description) // 200
    prefix = hashlib.sha256(description[:300].encode("utf-8")).hexdigest()[:16]
    return f"{company}|{length_bucket}|{prefix}"


def _descriptions_near_duplicate(
    left: dict[str, Any], right: dict[str, Any], config: dict[str, Any]
) -> bool:
    left_description = normalize_text(left.get("description", ""))[:8000]
    right_description = normalize_text(right.get("description", ""))[:8000]
    if not left_description or not right_description:
        return False
    shorter, longer = sorted((len(left_description), len(right_description)))
    if shorter / longer < 0.95:
        return False
    return SequenceMatcher(None, left_description, right_description).ratio() >= float(
        config.get("duplicate_cross_title_description_similarity", 0.97)
    )


def _similar_job(
    left: dict[str, Any], right: dict[str, Any], config: dict[str, Any] | None = None
) -> bool:
    config = config or {}
    left_title = normalize_title(left.get("title", ""))
    right_title = normalize_title(right.get("title", ""))
    title_ratio = SequenceMatcher(None, left_title, right_title).ratio()
    if title_ratio < float(config.get("duplicate_title_similarity", 0.9)):
        return False
    left_location = normalize_text(left.get("location", ""))
    right_location = normalize_text(right.get("location", ""))
    if left_location != right_location and not (left.get("remote") and right.get("remote")):
        return False
    left_description = normalize_text(left.get("description", ""))[:5000]
    right_description = normalize_text(right.get("description", ""))[:5000]
    return SequenceMatcher(None, left_description, right_description).ratio() >= float(
        config.get("duplicate_description_similarity", 0.88)
    )


def _merge_jobs(preferred: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if _job_preference(incoming) > _job_preference(preferred):
        base, other = incoming, preferred
    else:
        base, other = preferred, incoming
    merged = dict(base)
    merged["sources"] = sorted(set(preferred.get("sources", [])) | set(incoming.get("sources", [])))
    merged["source_urls"] = {**preferred.get("source_urls", {}), **incoming.get("source_urls", {})}
    merged["source_job_ids"] = {
        **preferred.get("source_job_ids", {}),
        **incoming.get("source_job_ids", {}),
    }
    if len(other.get("description", "")) > len(base.get("description", "")):
        merged["description"] = other["description"]
    merged["remote"] = bool(preferred.get("remote") or incoming.get("remote"))
    merged["hybrid"] = bool(preferred.get("hybrid") or incoming.get("hybrid"))
    merged["onsite"] = not merged["remote"] and not merged["hybrid"]
    merged["tags"] = sorted(set(preferred.get("tags", [])) | set(incoming.get("tags", [])))
    return merged


def _job_preference(job: dict[str, Any]) -> tuple[int, int, str]:
    location = normalize_text(job.get("location", ""))
    if "berlin" in location:
        location_priority = 4
    elif job.get("country") == "Germany" or "germany" in location or "deutschland" in location:
        location_priority = 3
    elif job.get("remote") and any(term in location for term in ("europe", "eu", "emea")):
        location_priority = 2
    elif job.get("remote"):
        location_priority = 1
    else:
        location_priority = 0
    return _source_quality(job), location_priority, str(job.get("published_at", ""))


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
