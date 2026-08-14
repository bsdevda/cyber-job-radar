from __future__ import annotations

import re
import time
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

        for index, company in enumerate(enabled_companies):
            try:
                payload = self._payload(company, fixture, result)
                for raw in payload.get("jobs", []):
                    if isinstance(raw, dict):
                        result.jobs.append(self._map_job(raw, company))
                result.companies_successful += 1
            except Exception as exc:
                error = self._error(str(company.get("name") or company.get("board")), exc)
                result.errors.append(error)
                result.companies_failed += 1
            if fixture is None and index + 1 < len(enabled_companies):
                delay = float(self.config.get("delay_seconds", 0.2))
                if delay:
                    time.sleep(delay)

        result.ok = result.companies_successful > 0
        if result.errors:
            result.error = result.errors[0]["message"]
        return result

    def _payload(
        self,
        company: dict[str, Any],
        fixture: dict[str, Any] | None,
        result: CollectionResult,
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
        result.requests += 1
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
