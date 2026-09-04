from __future__ import annotations

import re
from typing import Any

from .utils import normalize_text


DEFAULT_BERLIN_MARKERS = ("berlin",)


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
    "remote anywhere", "anywhere in the world",
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
    """Apply the user's strict work-location allowlist.

    Berlin vacancies may be on-site, hybrid or remote. Everywhere else must be
    explicitly remote and must say that Germany, Europe/EU/EMEA or the whole
    world is eligible. A generic "remote" label is deliberately insufficient.
    """
    policy = config.get("location_policy", {})
    location = normalize_text(job.get("location", ""))
    description = normalize_text(job.get("description", ""))[:5000]
    country = normalize_text(job.get("country", ""))
    remote = bool(job.get("remote")) or _has_remote_wording(location)
    hybrid = bool(job.get("hybrid"))

    berlin_markers = tuple(policy.get("berlin_markers", DEFAULT_BERLIN_MARKERS))
    germany_markers = tuple(policy.get("germany_markers", DEFAULT_GERMANY_MARKERS))
    europe_remote_markers = tuple(
        policy.get("europe_remote_markers", DEFAULT_EUROPE_REMOTE_MARKERS)
    )
    worldwide_markers = tuple(policy.get("worldwide_markers", DEFAULT_WORLDWIDE_MARKERS))
    restricted_markers = tuple(policy.get("restricted_markers", DEFAULT_RESTRICTED_MARKERS))

    location_scope = normalize_text(f"{location} {country}")
    combined = f" {location_scope} "
    berlin_location = any(
        _location_marker_matches(marker, location_scope, combined)
        for marker in berlin_markers
    )
    germany_location = (
        country == "germany"
        or any(
            _location_marker_matches(marker, location_scope, combined)
            for marker in germany_markers
        )
    )
    europe_location = (
        country == "europe"
        or location in {"europe", "european union", "eu", "eea", "emea"}
        or any(marker in location for marker in europe_remote_markers)
    )
    worldwide_location = (
        location in {"worldwide", "global", "anywhere"}
        or any(marker in location for marker in worldwide_markers)
    )
    germany_description = any(
        phrase in description
        for phrase in (
            "remote germany", "germany remote", "remote within germany",
            "remote from germany", "work remotely in germany",
            "work from home in germany", "home based in germany",
            "candidates based in germany", "candidates in germany",
        )
    )
    europe_description = any(marker in description for marker in europe_remote_markers)
    worldwide_description = any(marker in description for marker in worldwide_markers)
    remote = remote or germany_description or europe_description or worldwide_description

    if berlin_location:
        work_model = "Remote" if remote and not hybrid else "Hybrid" if hybrid else "On-site"
        return _result(
            "eligible_berlin",
            True,
            15,
            f"Berlin {work_model.lower()} role",
            scope="Berlin",
            work_model=work_model,
        )

    # Germany-wide vacancies are accepted only when they are remote. This
    # intentionally rejects on-site/hybrid roles in Munich, Hamburg, Frankfurt,
    # and every other non-Berlin city.
    if germany_location:
        if remote:
            return _result(
                "eligible_germany_remote",
                True,
                15,
                "Remote work from Germany is explicitly available",
                scope="Germany remote",
                work_model="Remote",
            )
        return _result(
            "ineligible_non_berlin_germany",
            False,
            0,
            "Germany role is on-site/hybrid outside Berlin; only Germany-remote roles are allowed",
            scope="Germany outside Berlin",
            work_model="Hybrid" if hybrid else "On-site",
        )

    if europe_location:
        if remote:
            return _result(
                "eligible_europe_remote",
                True,
                13,
                "Europe/EU/EMEA remote eligibility detected; verify Germany is an employing country",
                verification_required=True,
                score_cap=89,
                scope="Europe remote",
                work_model="Remote",
            )
        return _result(
            "ineligible_europe_not_remote",
            False,
            0,
            "Europe-wide location is not explicitly remote",
            scope="Europe",
            work_model="Hybrid" if hybrid else "On-site",
        )

    if worldwide_location:
        if remote:
            return _result(
                "eligible_worldwide_remote",
                True,
                11,
                "Worldwide/anywhere remote eligibility detected; verify employment from Germany",
                verification_required=True,
                score_cap=89,
                scope="Worldwide remote",
                work_model="Remote",
            )
        return _result(
            "ineligible_worldwide_not_remote",
            False,
            0,
            "Worldwide wording is present, but the vacancy is not explicitly remote",
            scope="Worldwide",
            work_model="On-site",
        )

    # A concrete non-target location takes precedence over generic remote or
    # worldwide wording copied into an employer description.
    if (
        any(
            _location_marker_matches(marker, location_scope, combined)
            for marker in restricted_markers
        )
        or (remote and not _is_generic_remote_location(location))
    ):
        return _result(
            "ineligible_restricted_region",
            False,
            0,
            "The vacancy has an explicit location outside Berlin/Germany-remote/Europe-remote/worldwide-remote scope",
            scope="Outside target",
            work_model="Remote" if remote else "Hybrid" if hybrid else "On-site",
        )

    if remote:
        if germany_description:
            return _result(
                "eligible_germany_remote",
                True,
                15,
                "Remote work from Germany is explicitly available in the vacancy text",
                scope="Germany remote",
                work_model="Remote",
            )
        if europe_description:
            return _result(
                "eligible_europe_remote",
                True,
                13,
                "Europe/EU/EMEA remote eligibility detected; verify Germany is an employing country",
                verification_required=True,
                score_cap=89,
                scope="Europe remote",
                work_model="Remote",
            )
        if worldwide_description:
            return _result(
                "eligible_worldwide_remote",
                True,
                11,
                "Worldwide/anywhere remote eligibility detected; verify employment from Germany",
                verification_required=True,
                score_cap=89,
                scope="Worldwide remote",
                work_model="Remote",
            )
        return _result(
            "remote_region_unclear",
            False,
            0,
            "Remote region is unclear; Germany, Europe/EU/EMEA, or worldwide eligibility is not explicit",
            scope="Remote region unclear",
            work_model="Remote",
        )

    if hybrid:
        return _result(
            "ineligible_hybrid_location_unclear",
            False,
            0,
            "Hybrid role is not located in Berlin",
            scope="Outside Berlin",
            work_model="Hybrid",
        )

    return _result(
        "ineligible_onsite_outside_germany",
        False,
        0,
        "On-site role is not located in Berlin",
        scope="Outside Berlin",
        work_model="On-site",
    )


def _has_remote_wording(value: str) -> bool:
    return bool(
        re.search(
            r"\b(?:remote|work from home|home[- ]based|fully distributed)\b",
            normalize_text(value),
        )
    )


def _is_generic_remote_location(value: str) -> bool:
    normalized = normalize_text(value).strip(" -/,|:")
    return normalized in {
        "",
        "remote",
        "remote region not stated",
        "location not stated",
        "unspecified",
        "work from home",
        "home based",
        "multiple locations",
    }


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
    scope: str = "",
    work_model: str = "",
) -> dict[str, Any]:
    return {
        "category": category,
        "eligible": eligible,
        "score": score,
        "reason": reason,
        "verification_required": verification_required,
        "score_cap": score_cap,
        "scope": scope,
        "work_model": work_model,
    }
