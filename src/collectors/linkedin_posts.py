from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
from xml.etree import ElementTree as ET

from .base import BaseCollector, CollectionResult
from ..utils import html_to_text, normalize_text


LINKEDIN_POST_PATHS = ("/posts/", "/feed/update/", "/pulse/")


class LinkedInPostsCollector(BaseCollector):
    """Collect public LinkedIn-post leads from user-authorized RSS/Atom feeds.

    This collector deliberately never requests linkedin.com, never uses login
    cookies and never automates a LinkedIn account. It only parses feed entries
    delivered to the user by a separate alert/feed service and retains entries
    that resolve to a public LinkedIn post URL.
    """

    name = "linkedin_posts"

    def collect(self, fixture_dir: Path | None = None) -> CollectionResult:
        result = CollectionResult(source=self.name)
        try:
            fixture = self._fixture(fixture_dir)
            if fixture is not None:
                entries = fixture.get("items", [])
                result.jobs.extend(self._map_entries(entries, "Offline LinkedIn post feed"))
                return result

            feeds = self._configured_feeds()
            if not feeds:
                return result

            successful = 0
            for feed in feeds:
                name = str(feed.get("name") or "LinkedIn public-post feed")
                url = str(feed.get("url") or "").strip()
                if not url:
                    continue
                try:
                    xml_text = self.client.get_text(
                        url,
                        accept="application/atom+xml, application/rss+xml, application/xml, text/xml",
                    )
                    result.requests += 1
                    entries = self._parse_feed(xml_text)
                    result.jobs.extend(self._map_entries(entries, name))
                    successful += 1
                except Exception as exc:
                    result.requests += 1
                    result.errors.append(self._error(name, exc))

            if feeds and successful == 0:
                result.ok = False
                result.error = result.errors[0]["message"] if result.errors else "No usable feeds"
        except Exception as exc:
            result.ok = False
            result.error = f"{type(exc).__name__}: {exc}"
        return result

    def _configured_feeds(self) -> list[dict[str, str]]:
        values: list[Any] = list(self.config.get("feeds", []))
        environment_name = str(
            self.config.get("feeds_env") or "LINKEDIN_POST_FEEDS_JSON"
        )
        environment_value = os.environ.get(environment_name, "").strip()
        if environment_value:
            try:
                parsed = json.loads(environment_value)
                if not isinstance(parsed, list):
                    raise ValueError("feed secret must be a JSON array")
                values.extend(parsed)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(
                    f"{environment_name} must be a JSON array of feed URLs or objects"
                ) from exc

        feeds: list[dict[str, str]] = []
        seen: set[str] = set()
        for index, value in enumerate(values, 1):
            if isinstance(value, str):
                feed = {"name": f"LinkedIn post feed {index}", "url": value}
            elif isinstance(value, dict):
                if value.get("enabled", True) is False:
                    continue
                feed = {
                    "name": str(value.get("name") or f"LinkedIn post feed {index}"),
                    "url": str(value.get("url") or ""),
                }
            else:
                raise ValueError("LinkedIn post feeds must be strings or objects")
            url = feed["url"].strip()
            if not url or url in seen:
                continue
            if urlsplit(url).scheme not in {"http", "https"}:
                raise ValueError("LinkedIn post feed URLs must use HTTP or HTTPS")
            seen.add(url)
            feeds.append({"name": feed["name"].strip(), "url": url})
        return feeds

    def _map_entries(
        self, entries: list[dict[str, Any]], feed_name: str
    ) -> list[dict[str, Any]]:
        maximum = max(1, int(self.config.get("max_items_per_feed", 50)))
        require_linkedin = bool(self.config.get("require_linkedin_post_url", True))
        mapped: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        for entry in entries[:maximum]:
            candidates = [
                str(entry.get("link") or ""),
                str(entry.get("guid") or ""),
                str(entry.get("description") or ""),
                str(entry.get("title") or ""),
            ]
            post_url = next(
                (url for value in candidates for url in _linkedin_urls(value)), ""
            )
            if require_linkedin and not post_url:
                continue
            source_url = post_url or str(entry.get("link") or "").strip()
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)
            title = _clean_title(str(entry.get("title") or "LinkedIn cybersecurity job lead"))
            summary = html_to_text(str(entry.get("description") or ""))
            combined = "\n\n".join(value for value in (title, summary) if value)
            if not _looks_like_security_job_lead(combined):
                continue
            author = html_to_text(str(entry.get("author") or "")).strip()
            location, remote = _infer_location(combined)
            source_id = str(entry.get("guid") or source_url)
            if len(source_id) > 180:
                source_id = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
            mapped.append(
                {
                    "source": "LinkedIn Posts",
                    "source_id": source_id,
                    "source_job_id": source_id,
                    "company": author or "LinkedIn public-post lead",
                    "title": title,
                    "location": location,
                    "remote": remote,
                    "url": source_url,
                    "apply_url": source_url,
                    "canonical_url": source_url,
                    "published_at": _normalize_published(str(entry.get("published_at") or "")),
                    "description": (
                        combined
                        + "\n\nPublic LinkedIn post lead. Verify the employer, active vacancy, "
                        "English working language, location, requirements and official application URL."
                    ),
                    "salary": "",
                    "employment_type": "",
                    "tags": ["LinkedIn post lead", feed_name],
                    "lead_type": "linkedin_post",
                    "post_author": author,
                    "feed_name": feed_name,
                }
            )
        return mapped

    @staticmethod
    def _parse_feed(xml_text: str) -> list[dict[str, str]]:
        root = ET.fromstring(xml_text)
        entries: list[dict[str, str]] = []
        for element in root.iter():
            if _local_name(element.tag) not in {"item", "entry"}:
                continue
            values: dict[str, str] = {
                "title": "",
                "link": "",
                "description": "",
                "published_at": "",
                "author": "",
                "guid": "",
            }
            for child in element.iter():
                name = _local_name(child.tag)
                text = "".join(child.itertext()).strip()
                if name == "title" and not values["title"]:
                    values["title"] = text
                elif name == "link" and not values["link"]:
                    values["link"] = str(child.attrib.get("href") or text)
                elif name in {"description", "summary", "content"} and not values["description"]:
                    values["description"] = text
                elif name in {"pubdate", "published", "updated", "date"} and not values["published_at"]:
                    values["published_at"] = text
                elif name in {"author", "creator"} and not values["author"]:
                    author_name = next(
                        (
                            "".join(descendant.itertext()).strip()
                            for descendant in child.iter()
                            if _local_name(descendant.tag) == "name"
                        ),
                        "",
                    )
                    values["author"] = author_name or text
                elif name in {"guid", "id"} and not values["guid"]:
                    values["guid"] = text
            entries.append(values)
        return entries

    def _error(self, feed_name: str, exc: Exception) -> dict[str, Any]:
        short = " ".join(str(exc).split())[:240]
        return {
            "source": self.name,
            "company": feed_name,
            "http_status": None,
            "exception_type": type(exc).__name__,
            "description": short,
            "message": f"LinkedIn Posts | {feed_name} | {type(exc).__name__} | {short}",
        }


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].casefold()


def _linkedin_urls(value: str) -> list[str]:
    decoded = html.unescape(unquote(value or ""))
    candidates = re.findall(r"https?://[^\s<>'\"]+", decoded, flags=re.IGNORECASE)
    expanded: list[str] = []
    for candidate in candidates:
        candidate = candidate.rstrip(".,);]")
        expanded.append(candidate)
        try:
            query = parse_qs(urlsplit(candidate).query)
        except ValueError:
            query = {}
        for key in ("url", "q", "target", "dest", "destination"):
            expanded.extend(query.get(key, []))
    output: list[str] = []
    for candidate in expanded:
        candidate = html.unescape(unquote(candidate)).rstrip(".,);]")
        try:
            parts = urlsplit(candidate)
        except ValueError:
            continue
        host = parts.netloc.casefold().removeprefix("www.")
        path = parts.path.casefold()
        if host.endswith("linkedin.com") and any(marker in path for marker in LINKEDIN_POST_PATHS):
            clean = f"https://www.linkedin.com{parts.path}"
            if clean not in output:
                output.append(clean)
    return output


def _looks_like_security_job_lead(value: str) -> bool:
    text = normalize_text(value)
    security = any(
        term in text
        for term in (
            "application security", "appsec", "product security", "security engineer",
            "security consultant", "penetration tester", "pentester", "vapt",
            "security tester", "vulnerability management", "cloud security",
            "devsecops", "soc analyst", "cybersecurity", "cyber security",
        )
    )
    hiring = any(
        term in text
        for term in (
            "hiring", "we are looking", "we re looking", "open role", "open position",
            "vacancy", "join our", "apply", "job opportunity", "career opportunity",
        )
    )
    return security and hiring


def _infer_location(value: str) -> tuple[str, bool]:
    text = normalize_text(value)
    if "berlin" in text:
        return "Berlin, Germany", "remote" in text
    if "remote germany" in text or "germany remote" in text:
        return "Remote Germany", True
    if any(term in text for term in ("germany", "deutschland", "munich", "hamburg")):
        return "Germany", "remote" in text
    if any(term in text for term in ("remote europe", "europe remote", "remote emea")):
        return "Europe Remote", True
    if "remote" in text:
        return "Remote - region not stated", True
    return "Location not stated", True


def _clean_title(value: str) -> str:
    title = html_to_text(value).strip()
    title = re.sub(r"\s*[-|]\s*LinkedIn\s*$", "", title, flags=re.IGNORECASE)
    return title[:240] or "LinkedIn cybersecurity job lead"


def _normalize_published(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except ValueError:
        return ""
