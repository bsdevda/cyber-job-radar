from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .base import BaseCollector, CollectionResult


class AshbyCollector(BaseCollector):
    """Collect listed vacancies from configured public Ashby job boards."""

    name = "ashby"

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
                    payload = self._payload(company, fixture)
                    self._record_success(result, company, payload)
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
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ashby") as executor:
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

    def _payload(self, company: dict[str, Any], fixture: dict[str, Any] | None) -> dict[str, Any]:
        board = str(company["board"])
        if fixture is not None:
            boards = fixture.get("boards")
            if not isinstance(boards, dict) or board not in boards:
                raise FileNotFoundError(f"No Ashby fixture for board '{board}'")
            payload = boards[board]
        else:
            payload = self.client.get_json(str(self.config["endpoint"]).format(board=board))
        if not isinstance(payload, dict):
            raise ValueError("Ashby response must be a JSON object")
        return payload

    def _record_success(
        self, result: CollectionResult, company: dict[str, Any], payload: dict[str, Any]
    ) -> None:
        jobs = payload.get("jobs", [])
        if not isinstance(jobs, list):
            raise ValueError("Ashby response jobs must be a list")
        for raw in jobs:
            if isinstance(raw, dict) and raw.get("isListed", True):
                result.jobs.append(self._map_job(raw, company))
        result.companies_successful += 1

    @staticmethod
    def _map_job(raw: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
        primary = str(raw.get("location") or "")
        locations = [primary] if primary else []
        for secondary in raw.get("secondaryLocations") or []:
            if isinstance(secondary, dict) and secondary.get("location"):
                value = str(secondary["location"])
                if value not in locations:
                    locations.append(value)
        job_url = str(raw.get("jobUrl") or "")
        source_id = str(raw.get("id") or urlsplit(job_url).path.rstrip("/").split("/")[-1])
        workplace = str(raw.get("workplaceType") or "").casefold()
        compensation = raw.get("compensation") if isinstance(raw.get("compensation"), dict) else {}
        tags = [str(value) for value in (raw.get("department"), raw.get("team")) if value]
        return {
            "source": "Ashby",
            "source_id": source_id,
            "source_job_id": source_id,
            "company": company.get("name") or "Unknown company",
            "title": raw.get("title") or "Untitled role",
            "location": " | ".join(locations),
            "remote": bool(raw.get("isRemote")) or workplace == "remote",
            "hybrid": workplace == "hybrid",
            "url": job_url,
            "apply_url": raw.get("applyUrl") or job_url,
            "canonical_url": job_url,
            "ats": "ashby",
            "published_at": raw.get("publishedAt") or "",
            "description": raw.get("descriptionPlain") or raw.get("descriptionHtml") or "",
            "salary": compensation.get("compensationTierSummary") or "",
            "employment_type": raw.get("employmentType") or "",
            "tags": tags,
        }

    def _record_failure(self, result: CollectionResult, company: dict[str, Any], exc: Exception) -> None:
        result.errors.append(self._error(str(company.get("name") or company.get("board")), exc))
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
        message = f"Ashby | {company} | {type(exc).__name__}"
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
