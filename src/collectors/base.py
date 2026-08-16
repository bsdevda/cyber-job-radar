from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..utils import HttpClient, load_json


@dataclass(slots=True)
class CollectionResult:
    source: str
    jobs: list[dict[str, Any]] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    errors: list[dict[str, Any]] = field(default_factory=list)
    requests: int = 0
    companies_checked: int = 0
    companies_successful: int = 0
    companies_failed: int = 0
    company_results: list[dict[str, Any]] = field(default_factory=list)


class Collector(Protocol):
    name: str

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult: ...


class BaseCollector:
    name = "base"

    def __init__(
        self,
        config: dict[str, Any],
        client: HttpClient,
        companies: list[dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.companies = companies or []

    def _fixture(self, fixture_dir: Path | None) -> dict[str, Any] | None:
        if fixture_dir is None:
            return None
        path = fixture_dir / f"{self.name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Offline fixture not found: {path}")
        return load_json(path)

    def _record_company_success(
        self,
        result: CollectionResult,
        company: dict[str, Any],
        jobs: int,
    ) -> None:
        result.company_results.append(
            {
                "source": self.name,
                "company": str(company.get("name") or self._company_identifier(company)),
                "identifier": self._company_identifier(company),
                "status": "ok",
                "jobs": max(0, int(jobs)),
                "http_status": None,
                "error": "",
            }
        )

    def _record_company_failure(
        self,
        result: CollectionResult,
        company: dict[str, Any],
        error: dict[str, Any],
    ) -> None:
        result.company_results.append(
            {
                "source": self.name,
                "company": str(company.get("name") or self._company_identifier(company)),
                "identifier": self._company_identifier(company),
                "status": "failed",
                "jobs": 0,
                "http_status": error.get("http_status"),
                "error": str(error.get("message") or error.get("description") or "")[:300],
            }
        )

    def _company_identifier(self, company: dict[str, Any]) -> str:
        field = {
            "greenhouse": "board",
            "ashby": "board",
            "lever": "site",
            "personio": "account",
            "recruitee": "subdomain",
        }.get(self.name, "identifier")
        return str(company.get(field) or "")
