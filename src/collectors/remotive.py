from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import BaseCollector, CollectionResult


class RemotiveCollector(BaseCollector):
    name = "remotive"

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult:
        result = CollectionResult(source=self.name)
        try:
            payload = self._fixture(fixture_dir)
            if payload is None:
                payload = self.client.get_json(str(self.config["endpoint"]))
                result.requests += 1
            for raw in payload.get("jobs", []):
                result.jobs.append(self._map_job(raw))
        except Exception as exc:
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
        return result

    @staticmethod
    def _map_job(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "Remotive",
            "source_id": str(raw.get("id") or ""),
            "company": raw.get("company_name") or "Unknown company",
            "title": raw.get("title") or "Untitled role",
            "location": raw.get("candidate_required_location") or "Remote",
            "remote": True,
            "url": raw.get("url") or "",
            "published_at": raw.get("publication_date") or "",
            "description": raw.get("description") or "",
            "salary": raw.get("salary") or "",
            "employment_type": raw.get("job_type") or "",
            "tags": raw.get("tags") or [],
        }
