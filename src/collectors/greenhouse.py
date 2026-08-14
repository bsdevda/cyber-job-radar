from __future__ import annotations

import re
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .base import BaseCollector, CollectionResult


class GreenhouseCollector(BaseCollector):
    """Collect published vacancies from configured public Greenhouse boards."""

    name = "greenhouse"

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult:
        result = CollectionResult(source=self.name)
        enabled_companies = [company for company in self.companies if company.get("enabled", True)]
        result.companies_checked = len(enabled_companies)
        if not enabled_companies:
            return result

        fixture = None
        if fixture_dir is not None:
            try:
                fixture = self._fixture(fixture_dir)
            except Exception as exc:
                error = self._error("all configured companies", exc)
                result.ok = False
                result.error = error["message"]
                result.errors.append(error)
                result.companies_failed = result.companies_checked
                return result

        if fixture is not None:
            self._collect_sequential(enabled_companies, fixture, result)
        else:
            self._collect_parallel(enabled_companies, result)

        result.ok = result.companies_successful > 0
        if result.errors:
            result.error = result.errors[0]["message"]
        return result

    def _collect_sequential(
        self,
        companies: list[dict[str, Any]],
        fixture: dict[str, Any],
        result: CollectionResult,
    ) -> None:
        """Keep fixture collection deterministic and free from test-only threads."""
        for company in companies:
            try:
                payload = self._payload(company, fixture)
                self._record_success(result, company, payload)
            except Exception as exc:
                self._record_failure(result, company, exc)

    def _collect_parallel(
        self,
        companies: list[dict[str, Any]],
        result: CollectionResult,
    ) -> None:
        """Fetch live boards concurrently while preserving configured result order."""
        configured_workers = int(self.config.get("max_workers", 6))
        max_workers = max(1, min(configured_workers, 12, len(companies)))
        delay = max(0.0, float(self.config.get("delay_seconds", 0.05)))
        futures: list[tuple[dict[str, Any], Future[dict[str, Any]]]] = []

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="greenhouse",
        ) as executor:
            for index, company in enumerate(companies):
                futures.append((company, executor.submit(self._payload, company, None)))
                result.requests += 1
                if delay and index + 1 < len(companies):
                    time.sleep(delay)

            # Iterating the future list instead of as_completed keeps jobs and
            # diagnostics stable between runs without making requests sequential.
            for company, future in futures:
                try:
                    self._record_success(result, company, future.result())
                except Exception as exc:
                    self._record_failure(result, company, exc)

    def _record_success(
        self,
        result: CollectionResult,
        company: dict[str, Any],
        payload: dict[str, Any],
    ) -> None:
        for raw in payload.get("jobs", []):
            if isinstance(raw, dict):
                result.jobs.append(self._map_job(raw, company))
        result.companies_successful += 1

    def _record_failure(
        self,
        result: CollectionResult,
        company: dict[str, Any],
        exc: Exception,
    ) -> None:
        label = str(company.get("name") or company.get("board"))
        result.errors.append(self._error(label, exc))
        result.companies_failed += 1

    def _payload(
        self,
        company: dict[str, Any],
        fixture: dict[str, Any] | None,
    ) -> dict[str, Any]:
        board = str(company["board"])
        if fixture is not None:
            boards = fixture.get("boards")
            if not isinstance(boards, dict) or board not in boards:
                raise FileNotFoundError(f"No Greenhouse fixture for board '{board}'")
            payload = boards[board]
            if not isinstance(payload, dict):
                raise ValueError(f"Greenhouse fixture for board '{board}' must be an object")
            return payload

        endpoint = str(self.config["endpoint"]).format(board=board)
        payload = self.client.get_json(endpoint)
        if not isinstance(payload, dict):
            raise ValueError("Greenhouse response must be a JSON object")
        return payload

    @staticmethod
    def _map_job(raw: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), list) else []
        employment_type = ""
        for entry in metadata:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").casefold()
            if "employment" in name or "job type" in name:
                employment_type = str(entry.get("value") or "")
                break

        tags: list[str] = []
        for group in (raw.get("departments"), raw.get("offices")):
            if isinstance(group, list):
                tags.extend(str(item.get("name")) for item in group if isinstance(item, dict) and item.get("name"))

        url = str(raw.get("absolute_url") or "")
        location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
        return {
            "source": "Greenhouse",
            "source_id": str(raw.get("id") or ""),
            "source_job_id": str(raw.get("id") or ""),
            "company": company.get("name") or "Unknown company",
            "title": raw.get("title") or "Untitled role",
            "location": location.get("name") or "",
            "remote": False,
            "url": url,
            "apply_url": url,
            "canonical_url": url,
            "ats": "greenhouse",
            "published_at": raw.get("updated_at") or "",
            "description": raw.get("content") or "",
            "salary": "",
            "employment_type": employment_type,
            "tags": tags,
        }

    def _error(self, company: str, exc: Exception) -> dict[str, Any]:
        short = " ".join(str(exc).split())[:240]
        status_match = re.search(r"(?:HTTP(?: Error)?\s*)(\d{3})", short, flags=re.IGNORECASE)
        status = int(status_match.group(1)) if status_match else None
        message = f"Greenhouse | {company} | {type(exc).__name__}"
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
