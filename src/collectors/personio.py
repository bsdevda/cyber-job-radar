from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .base import BaseCollector, CollectionResult


class PersonioCollector(BaseCollector):
    """Collect vacancies from configured public Personio XML career feeds."""

    name = "personio"

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult:
        result = CollectionResult(source=self.name)
        companies = [company for company in self.companies if company.get("enabled", True)]
        result.companies_checked = len(companies)
        if not companies:
            return result
        fixture_text = None
        if fixture_dir is not None:
            path = fixture_dir / "personio.xml"
            if not path.exists():
                self._record_total_failure(result, companies, FileNotFoundError(f"Offline fixture not found: {path}"))
                return result
            fixture_text = path.read_text(encoding="utf-8")
        if fixture_text is not None:
            for company in companies:
                try:
                    self._record_success(result, company, self._positions(fixture_text, company))
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
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="personio") as executor:
            for index, company in enumerate(companies):
                futures.append((company, executor.submit(self._fetch_positions, company)))
                result.requests += 1
                if delay and index + 1 < len(companies):
                    time.sleep(delay)
            for company, future in futures:
                try:
                    self._record_success(result, company, future.result())
                except Exception as exc:
                    self._record_failure(result, company, exc)

    def _fetch_positions(self, company: dict[str, Any]) -> list[dict[str, Any]]:
        account = str(company["account"])
        language = str(company.get("language") or "en")
        endpoint = str(self.config["endpoint"]).format(account=account, language=quote(language))
        return self._positions(self.client.get_text(endpoint), company)

    def _positions(self, xml_text: str, company: dict[str, Any]) -> list[dict[str, Any]]:
        root = ET.fromstring(xml_text)
        return [self._map_position(position, company) for position in root.findall(".//position")]

    def _record_success(
        self, result: CollectionResult, company: dict[str, Any], jobs: list[dict[str, Any]]
    ) -> None:
        result.jobs.extend(jobs)
        result.companies_successful += 1

    @staticmethod
    def _map_position(position: ET.Element, company: dict[str, Any]) -> dict[str, Any]:
        def text(path: str) -> str:
            value = position.findtext(path)
            return value.strip() if value else ""

        description_parts: list[str] = []
        for block in position.findall("./jobDescriptions/jobDescription"):
            heading = (block.findtext("name") or "").strip()
            value = (block.findtext("value") or "").strip()
            if heading or value:
                description_parts.append(f"{heading}\n{value}".strip())
        experience = text("yearsOfExperience")
        experience_map = {
            "lt-1": "Less than 1 year of experience",
            "1-2": "1-2 years of experience",
            "2-5": "2-5 years of experience",
            "5-7": "5-7 years of experience",
            "7-10": "7-10 years of experience",
            "10-15": "10-15 years of experience",
            "gt-15": "15+ years of experience",
        }
        if experience in experience_map:
            description_parts.append(experience_map[experience])
        account = str(company["account"])
        language = str(company.get("language") or "en")
        source_id = text("id")
        url = f"https://{account}.jobs.personio.de/job/{source_id}?language={quote(language)}"
        tags = [
            value
            for value in (text("department"), text("recruitingCategory"), text("seniority"), experience)
            if value
        ]
        employment = " / ".join(value for value in (text("employmentType"), text("schedule")) if value)
        return {
            "source": "Personio",
            "source_id": source_id,
            "source_job_id": source_id,
            "company": text("subcompany") or company.get("name") or "Unknown company",
            "title": text("name") or "Untitled role",
            "location": text("office"),
            "remote": "remote" in text("office").casefold(),
            "url": url,
            "apply_url": url,
            "canonical_url": url,
            "ats": "personio",
            "published_at": text("createdAt"),
            "description": "\n\n".join(description_parts),
            "salary": "",
            "employment_type": employment,
            "tags": tags,
        }

    def _record_failure(self, result: CollectionResult, company: dict[str, Any], exc: Exception) -> None:
        result.errors.append(self._error(str(company.get("name") or company.get("account")), exc))
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
        message = f"Personio | {company} | {type(exc).__name__}"
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
