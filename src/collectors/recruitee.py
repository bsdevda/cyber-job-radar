from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .base import BaseCollector, CollectionResult


class RecruiteeCollector(BaseCollector):
    """Collect published offers from public Recruitee career-site feeds."""

    name = "recruitee"

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult:
        result = CollectionResult(source=self.name)
        companies = [company for company in self.companies if company.get("enabled", True)]
        result.companies_checked = len(companies)
        if not companies:
            return result
        fixture = None
        if fixture_dir is not None:
            try:
                fixture = self._fixture(fixture_dir)
            except Exception as exc:
                self._record_total_failure(result, companies, exc)
                return result
        if fixture is not None:
            for company in companies:
                try:
                    self._record_success(result, company, self._payload(company, fixture))
                except Exception as exc:
                    self._record_failure(result, company, exc)
        else:
            self._collect_parallel(companies, result)
        result.ok = result.companies_successful > 0
        if result.errors:
            result.error = result.errors[0]["message"]
        return result

    def _collect_parallel(self, companies: list[dict[str, Any]], result: CollectionResult) -> None:
        workers = max(1, min(int(self.config.get("max_workers", 6)), 12, len(companies)))
        delay = max(0.0, float(self.config.get("delay_seconds", 0.05)))
        futures: list[tuple[dict[str, Any], Future[dict[str, Any]]]] = []
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="recruitee") as executor:
            for index, company in enumerate(companies):
                futures.append((company, executor.submit(self._payload, company, None)))
                result.requests += 1
                if delay and index + 1 < len(companies):
                    time.sleep(delay)
            for company, future in futures:
                try:
                    self._record_success(result, company, future.result())
                except Exception as exc:
                    self._record_failure(result, company, exc)

    def _payload(
        self, company: dict[str, Any], fixture: dict[str, Any] | None
    ) -> dict[str, Any]:
        subdomain = str(company["subdomain"])
        if fixture is not None:
            tenants = fixture.get("subdomains")
            if not isinstance(tenants, dict) or subdomain not in tenants:
                raise FileNotFoundError(f"No Recruitee fixture for subdomain '{subdomain}'")
            payload = tenants[subdomain]
        else:
            payload = self.client.get_json(
                str(self.config["endpoint"]).format(subdomain=subdomain)
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("offers", []), list):
            raise ValueError("Recruitee response must contain an offers list")
        return payload

    def _record_success(
        self, result: CollectionResult, company: dict[str, Any], payload: dict[str, Any]
    ) -> None:
        before = len(result.jobs)
        for raw in payload.get("offers", []):
            if isinstance(raw, dict) and str(raw.get("status") or "published") == "published":
                result.jobs.append(self._map_job(raw, company))
        result.companies_successful += 1
        self._record_company_success(result, company, len(result.jobs) - before)

    @staticmethod
    def _map_job(raw: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
        salary_data = raw.get("salary") if isinstance(raw.get("salary"), dict) else {}
        salary_parts = [
            salary_data.get("currency"),
            salary_data.get("min"),
            "-" if salary_data.get("min") is not None and salary_data.get("max") is not None else None,
            salary_data.get("max"),
            salary_data.get("period"),
        ]
        salary = " ".join(str(value) for value in salary_parts if value not in {None, ""})
        description = "\n\n".join(
            str(value)
            for value in (raw.get("description"), raw.get("requirements"))
            if value
        )
        tags = [
            str(value)
            for value in (raw.get("department"), raw.get("category_code"), raw.get("experience_code"))
            if value
        ]
        return {
            "source": "Recruitee",
            "source_id": str(raw.get("id") or raw.get("guid") or raw.get("slug") or ""),
            "source_job_id": str(raw.get("id") or raw.get("guid") or raw.get("slug") or ""),
            "company": company.get("name") or raw.get("company_name") or "Unknown company",
            "title": raw.get("title") or "Untitled role",
            "location": raw.get("location") or "",
            "remote": bool(raw.get("remote")),
            "hybrid": bool(raw.get("hybrid")),
            "url": raw.get("careers_url") or "",
            "apply_url": raw.get("careers_apply_url") or raw.get("careers_url") or "",
            "canonical_url": raw.get("careers_url") or "",
            "ats": "recruitee",
            "published_at": raw.get("published_at") or raw.get("created_at") or "",
            "description": description,
            "salary": salary,
            "employment_type": raw.get("employment_type_code") or "",
            "tags": tags,
        }

    def _record_failure(self, result: CollectionResult, company: dict[str, Any], exc: Exception) -> None:
        error = self._error(str(company.get("name") or company.get("subdomain")), exc)
        result.errors.append(error)
        result.companies_failed += 1
        self._record_company_failure(result, company, error)

    def _record_total_failure(
        self, result: CollectionResult, companies: list[dict[str, Any]], exc: Exception
    ) -> None:
        result.ok = False
        result.companies_failed = len(companies)
        error = self._error("all configured companies", exc)
        result.errors.append(error)
        result.error = error["message"]

    def _error(self, company: str, exc: Exception) -> dict[str, Any]:
        short = " ".join(str(exc).split())[:240]
        status_match = re.search(r"HTTP(?: Error)?\s*(\d{3})", short, flags=re.IGNORECASE)
        status = int(status_match.group(1)) if status_match else None
        message = f"Recruitee | {company} | {type(exc).__name__}"
        if status is not None:
            message += f" | HTTP {status}"
        if short:
            message += f" | {short}"
        return {
            "source": self.name,
            "company": company,
            "http_status": status,
            "exception_type": type(exc).__name__,
            "description": short,
            "message": message,
        }
