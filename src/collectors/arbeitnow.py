from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .base import BaseCollector, CollectionResult


class ArbeitnowCollector(BaseCollector):
    name = "arbeitnow"

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult:
        result = CollectionResult(source=self.name)
        try:
            fixture = self._fixture(fixture_dir)
            if fixture is not None:
                pages = fixture.get("pages", [fixture])
            else:
                pages = self._fetch_pages(result)
            for page in pages:
                for raw in page.get("data", []):
                    result.jobs.append(self._map_job(raw))
        except Exception as exc:
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
        return result

    def _fetch_pages(self, result: CollectionResult) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        max_pages = int(self.config.get("max_pages", 5))
        delay = float(self.config.get("delay_seconds", 0.35))
        endpoint = str(self.config["endpoint"])
        for page_number in range(1, max_pages + 1):
            separator = "&" if "?" in endpoint else "?"
            payload = self.client.get_json(f"{endpoint}{separator}{urlencode({'page': page_number})}")
            result.requests += 1
            pages.append(payload)
            data = payload.get("data", [])
            if not data or not payload.get("links", {}).get("next"):
                break
            if delay:
                time.sleep(delay)
        return pages

    @staticmethod
    def _map_job(raw: dict[str, Any]) -> dict[str, Any]:
        created_at = raw.get("created_at")
        if isinstance(created_at, (int, float)):
            published_at = datetime.fromtimestamp(created_at, tz=UTC).isoformat().replace("+00:00", "Z")
        else:
            published_at = str(created_at or "")
        return {
            "source": "Arbeitnow",
            "source_id": str(raw.get("slug") or ""),
            "company": raw.get("company_name") or "Unknown company",
            "title": raw.get("title") or "Untitled role",
            "location": raw.get("location") or "",
            "remote": bool(raw.get("remote")),
            "url": raw.get("url") or "",
            "published_at": published_at,
            "description": raw.get("description") or "",
            "salary": raw.get("salary") or "",
            "employment_type": ", ".join(raw.get("job_types") or []),
            "tags": raw.get("tags") or [],
        }
