from __future__ import annotations

import re
from typing import Any

from .utils import normalize_text


DEFAULT_GERMANY_MARKERS = (
    "berlin", "germany", "deutschland", "munich", "münchen", "hamburg",
    "frankfurt", "cologne", "köln", "düsseldorf", "dusseldorf", "stuttgart",
    "leipzig", "dresden", "potsdam", "bonn", "bremen", "hannover", "hanover",
    "nuremberg", "nürnberg",
)

DEFAULT_EUROPE_REMOTE_MARKERS = (
    "europe remote", "remote europe", "european remote", "eu remote", "remote eu",
    "europe, remote", "europe-wide", "across europe", "emea remote", "remote emea",
)

DEFAULT_WORLDWIDE_MARKERS = (
    "worldwide", "anywhere", "global remote", "remote global", "work from anywhere",
)

DEFAULT_RESTRICTED_MARKERS = (
    "united states", "usa", "u.s.", "us", "canada", "united kingdom", "uk", "india",
    "australia", "china", "japan", "singapore", "brazil", "mexico", "south africa",
    "poland", "netherlands", "france", "spain", "portugal", "italy", "ireland",
    "sweden", "denmark", "norway", "finland", "switzerland", "austria", "belgium",
    "czech republic", "czechia", "romania", "hungary", "greece", "croatia", "serbia",
    "bulgaria", "slovakia", "slovenia", "estonia", "latvia", "lithuania", "ukraine",
    "san francisco", "new york", "seattle", "boston", "california", "washington,",
    "texas", "florida", "chicago", "palo alto", "redmond", "hawthorne", "omaha",
    "bellevue", "menlo park", "north america",
    "alabama", "alaska", "arizona", "arkansas", "colorado", "connecticut",
    "delaware", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
    "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska",
    "nevada", "new hampshire", "new jersey", "new mexico", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island",
    "south carolina", "south dakota", "tennessee", "utah", "vermont", "virginia",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
)


def assess_location(job: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    policy = config.get("location_policy", {})
    location = normalize_text(job.get("location", ""))
    description = normalize_text(job.get("description", ""))[:5000]
    country = normalize_text(job.get("country", ""))
    remote = bool(job.get("remote"))
    hybrid = bool(job.get("hybrid"))

    germany_markers = tuple(policy.get("germany_markers", DEFAULT_GERMANY_MARKERS))
    europe_remote_markers = tuple(
        policy.get("europe_remote_markers", DEFAULT_EUROPE_REMOTE_MARKERS)
    )
    worldwide_markers = tuple(policy.get("worldwide_markers", DEFAULT_WORLDWIDE_MARKERS))
    restricted_markers = tuple(policy.get("restricted_markers", DEFAULT_RESTRICTED_MARKERS))

    location_scope = normalize_text(f"{location} {country}")
    combined = f" {location_scope} "
    germany_location = any(marker in location for marker in germany_markers) or country == "germany"
    germany_description = any(
        phrase in description
        for phrase in (
            "based in germany", "located in germany", "remote from germany",
            "work remotely in germany", "candidates in germany",
        )
    )
    if germany_location:
        return _result("eligible_germany", True, 15, "Germany/Berlin eligibility detected")

    if any(_location_marker_matches(marker, location_scope, combined) for marker in restricted_markers):
        return _result(
            "ineligible_restricted_region",
            False,
            0,
            "The vacancy is restricted to a country/region outside the Germany or Europe-remote target",
        )

    if germany_description:
        return _result("eligible_germany", True, 15, "Germany eligibility detected in the vacancy text")

    if remote and (
        country == "europe"
        or location in {"europe", "european union", "eu", "emea"}
        or any(marker in location or marker in description for marker in europe_remote_markers)
    ):
        return _result("eligible_europe_remote", True, 13, "Europe/EMEA remote eligibility detected")

    # An explicit vacancy location such as "Remote - US" or "London, UK" must
    # take precedence over generic "global/worldwide" employer copy in the
    # description. This avoids accepting region-locked jobs because the footer
    # describes the company as globally distributed.
    if remote and any(marker in location for marker in worldwide_markers):
        return _result(
            "eligible_worldwide_remote",
            True,
            11,
            "Worldwide remote wording detected; verify employment availability in Germany",
            verification_required=True,
            score_cap=79,
        )

    if remote:
        return _result(
            "remote_region_unclear",
            True,
            6,
            "Remote role, but Germany/Europe eligibility is not explicit",
            verification_required=True,
            score_cap=59,
        )

    if hybrid:
        return _result(
            "ineligible_hybrid_location_unclear",
            False,
            0,
            "Hybrid role without a confirmed Germany location",
        )

    return _result(
        "ineligible_onsite_outside_germany",
        False,
        0,
        "On-site location is outside Germany or cannot be confirmed as Germany",
    )


def _location_marker_matches(marker: str, location: str, combined: str) -> bool:
    marker = normalize_text(marker)
    if not marker:
        return False
    # Short country codes need token boundaries so "us" cannot match an
    # unrelated word such as "business".
    if len(marker) <= 3:
        return re.search(rf"(?<![a-z]){re.escape(marker)}(?![a-z])", location) is not None
    return f" {marker} " in combined or marker in location


def _result(
    category: str,
    eligible: bool,
    score: int,
    reason: str,
    *,
    verification_required: bool = False,
    score_cap: int | None = None,
) -> dict[str, Any]:
    return {
        "category": category,
        "eligible": eligible,
        "score": score,
        "reason": reason,
        "verification_required": verification_required,
        "score_cap": score_cap,
    }
