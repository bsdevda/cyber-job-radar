from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


LOGGER = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "br", "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4",
        "section", "article", "tr", "td",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(value: str | None) -> str:
    """Convert HTML or escaped HTML into compact readable text."""
    if not value:
        return ""
    decoded = value
    for _ in range(2):
        decoded = html.unescape(decoded)
    parser = _TextExtractor()
    try:
        parser.feed(decoded)
        text = "".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", decoded)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_text(value: str | None) -> str:
    value = html_to_text(value).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9äöüß+/#. -]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read valid JSON from {path}: {exc}") from exc


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temp_name = handle.name
    os.replace(temp_name, path)


def write_text_atomic(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(value)
        temp_name = handle.name
    os.replace(temp_name, path)


def iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class HttpClient:
    timeout_seconds: int = 25
    retries: int = 3
    backoff_seconds: float = 1.0
    user_agent: str = "CyberJobRadar/1.0"

    def get_json(self, url: str) -> Any:
        return json.loads(self.get_text(url, accept="application/json"))

    def get_text(self, url: str, accept: str = "text/plain, application/xml, text/xml") -> str:
        request = Request(
            url,
            headers={
                "Accept": accept,
                "User-Agent": self.user_agent,
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset)
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else self._delay(attempt)
            except (URLError, TimeoutError) as exc:
                last_error = exc
                delay = self._delay(attempt)
            if attempt + 1 < self.retries:
                LOGGER.warning("Request failed (%s); retrying in %.1fs: %s", attempt + 1, delay, url)
                time.sleep(delay)
        raise RuntimeError(f"Request failed after {self.retries} attempt(s): {url}: {last_error}")

    def _delay(self, attempt: int) -> float:
        return self.backoff_seconds * (2**attempt)
