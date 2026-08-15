from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .base import BaseCollector, CollectionResult


class LeverCollector(BaseCollector):
    """Collect public Lever postings from global and EU instances."""

    name = "lever"

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
        futures: list[tuple[dict[str, Any], Future[list[dict[str, Any]]]]] = []
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="lever") as executor:
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
    ) -> list[dict[str, Any]]:
        site = str(company["site"])
        if fixture is not None:
            sites = fixture.get("sites")
            if not isinstance(sites, dict) or site not in sites:
                raise FileNotFoundError(f"No Lever fixture for site '{site}'")
            payload = sites[site]
        else:
            endpoint_key = "eu_endpoint" if company.get("region") == "eu" else "endpoint"
            payload = self.client.get_json(str(self.config[endpoint_key]).format(site=site))
        if not isinstance(payload, list):
            raise ValueError("Lever response must be a JSON list")
        return payload

    def _record_success(
        self, result: CollectionResult, company: dict[str, Any], payload: list[dict[str, Any]]
    ) -> None:
        for raw in payload:
            if isinstance(raw, dict):
                result.jobs.append(self._map_job(raw, company))
        result.companies_successful += 1

    @staticmethod
    def _map_job(raw: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
        categories = raw.get("categories") if isinstance(raw.get("categories"), dict) else {}
        locations: list[str] = []
        for value in [categories.get("location"), *(categories.get("allLocations") or [])]:
            if value and str(value) not in locations:
                locations.append(str(value))
        lists = raw.get("lists") if isinstance(raw.get("lists"), list) else []
        list_text = "\n".join(
            f"{item.get('text', '')}\n{item.get('content', '')}" for item in lists if isinstance(item, dict)
        )
        description = "\n".join(
            value
            for value in (
                str(raw.get("descriptionPlain") or raw.get("description") or ""),
                list_text,
                str(raw.get("additionalPlain") or raw.get("additional") or ""),
            )
            if value
        )
        workplace = str(raw.get("workplaceType") or "").casefold()
        salary_range = raw.get("salaryRange") if isinstance(raw.get("salaryRange"), dict) else {}
        salary = str(raw.get("salaryDescriptionPlain") or "")
        if not salary and salary_range:
            salary = " ".join(
                str(value)
                for value in (
                    salary_range.get("currency"), salary_range.get("min"), "-",
                    salary_range.get("max"), salary_range.get("interval"),
                )
                if value is not None
            )
        tags = [
            str(categories[key]) for key in ("team", "department") if categories.get(key)
        ]
        return {
            "source": "Lever",
            "source_id": str(raw.get("id") or ""),
            "source_job_id": str(raw.get("id") or ""),
            "company": company.get("name") or "Unknown company",
            "title": raw.get("text") or "Untitled role",
            "location": " | ".join(locations),
            "remote": workplace == "remote",
            "hybrid": workplace == "hybrid",
            "url": raw.get("hostedUrl") or "",
            "apply_url": raw.get("applyUrl") or raw.get("hostedUrl") or "",
            "canonical_url": raw.get("hostedUrl") or "",
            "ats": "lever",
            "published_at": _lever_datetime(raw.get("createdAt")),
            "description": description,
            "salary": salary,
            "employment_type": categories.get("commitment") or "",
            "tags": tags,
        }

    def _record_failure(self, result: CollectionResult, company: dict[str, Any], exc: Exception) -> None:
        result.errors.append(self._error(str(company.get("name") or company.get("site")), exc))
        result.companies_failed += 1

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
        message = f"Lever | {company} | {type(exc).__name__}"
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


def _lever_datetime(value: Any) -> str:
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat().replace("+00:00", "Z")
    return str(value or "")
