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
    requests: int = 0


class Collector(Protocol):
    name: str

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult: ...


class BaseCollector:
    name = "base"

    def __init__(self, config: dict[str, Any], client: HttpClient) -> None:
        self.config = config
        self.client = client

    def _fixture(self, fixture_dir: Path | None) -> dict[str, Any] | None:
        if fixture_dir is None:
            return None
        path = fixture_dir / f"{self.name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Offline fixture not found: {path}")
        return load_json(path)
