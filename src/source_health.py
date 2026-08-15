from __future__ import annotations

from typing import Any

from .collectors.base import CollectionResult


COMPANY_SOURCES = {"greenhouse", "ashby", "lever", "personio"}


def build_source_health(
    results: list[CollectionResult], generated_at: str
) -> dict[str, Any]:
    sources: dict[str, dict[str, Any]] = {}
    for result in results:
        is_company_source = result.companies_checked > 0 or result.source in COMPANY_SOURCES
        if is_company_source and result.companies_checked == 0:
            status = "idle"
        elif is_company_source and result.companies_failed and result.companies_successful:
            status = "partial"
        elif not result.ok:
            status = "failed"
        else:
            status = "ok"

        errors = list(result.errors)
        if result.error and not errors:
            errors.append(
                {
                    "source": result.source,
                    "company": "",
                    "http_status": None,
                    "exception_type": "CollectorError",
                    "description": result.error[:240],
                    "message": result.error[:300],
                }
            )
        details: dict[str, Any] = {
            "status": status,
            "ok": status in {"ok", "partial", "idle"},
            "jobs": len(result.jobs),
            "requests": result.requests,
            "errors": errors,
            "error": result.error,
        }
        if is_company_source:
            details.update(
                {
                    "companies_checked": result.companies_checked,
                    "companies_successful": result.companies_successful,
                    "companies_failed": result.companies_failed,
                }
            )
        sources[result.source] = details

    operational = [details for details in sources.values() if details["status"] != "idle"]
    return {
        "generated_at": generated_at,
        "all_sources_failed": bool(operational)
        and all(details["status"] == "failed" for details in operational),
        "sources": sources,
    }
