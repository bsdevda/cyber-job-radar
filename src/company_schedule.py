from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any


IDENTIFIER_FIELDS = {
    "greenhouse": "board",
    "ashby": "board",
    "lever": "site",
    "personio": "account",
    "recruitee": "subdomain",
}


def select_companies(
    source: str,
    companies: list[dict[str, Any]],
    health: dict[str, Any],
    generated_at: str,
    mode: str,
    options: dict[str, Any],
    fixture_mode: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select an auditable, deterministic employer batch for one ATS."""
    if mode not in {"daily", "full"}:
        raise ValueError("Employer scan mode must be 'daily' or 'full'")
    identifier_field = IDENTIFIER_FIELDS[source]
    enabled = [company for company in companies if company.get("enabled", True)]
    enabled.sort(
        key=lambda company: (
            not bool(company.get("priority", False)),
            str(company.get("name") or "").casefold(),
            str(company.get(identifier_field) or "").casefold(),
        )
    )
    if fixture_mode:
        return enabled, _summary(source, mode, enabled, enabled, [], [], None)

    now = _parse_time(generated_at)
    batch_count = max(1, int(options.get("daily_batch_count", 5)))
    batch_index = now.weekday() % batch_count
    employer_health = health.get("employers", {}) if isinstance(health, dict) else {}
    selected: list[dict[str, Any]] = []
    rotation_skips: list[str] = []
    cooldown_skips: list[str] = []

    for company in enabled:
        identifier = str(company[identifier_field])
        key = company_key(source, identifier)
        entry = employer_health.get(key, {})
        if _cooldown_active(entry.get("next_retry_at"), now):
            cooldown_skips.append(key)
            continue
        is_priority = bool(company.get("priority", False))
        scheduled = mode == "full" or is_priority or _bucket(key, batch_count) == batch_index
        if scheduled:
            selected.append(company)
        else:
            rotation_skips.append(key)

    limit_key = "full_company_limit_per_source" if mode == "full" else "daily_company_limit_per_source"
    limit = max(1, int(options.get(limit_key, 500)))
    if len(selected) > limit:
        overflow = selected[limit:]
        rotation_skips.extend(
            company_key(source, str(company[identifier_field])) for company in overflow
        )
        selected = selected[:limit]
    return selected, _summary(
        source,
        mode,
        enabled,
        selected,
        rotation_skips,
        cooldown_skips,
        batch_index if mode == "daily" else None,
    )


def update_company_health(
    existing: dict[str, Any],
    companies_config: dict[str, Any],
    results: list[Any],
    selection: dict[str, Any],
    generated_at: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    now = _parse_time(generated_at)
    employers = dict(existing.get("employers", {})) if isinstance(existing, dict) else {}
    configured_keys: set[str] = set()

    for source, identifier_field in IDENTIFIER_FIELDS.items():
        for company in companies_config.get(source, []):
            identifier = str(company.get(identifier_field) or "")
            if not identifier:
                continue
            key = company_key(source, identifier)
            configured_keys.add(key)
            entry = dict(employers.get(key, {}))
            entry.update(
                {
                    "source": source,
                    "company": str(company.get("name") or identifier),
                    "identifier": identifier,
                    "enabled": bool(company.get("enabled", True)),
                    "priority": bool(company.get("priority", False)),
                    "category": str(company.get("category") or ""),
                    "current_security_hiring": bool(
                        company.get("current_security_hiring", False)
                    ),
                    "security_hiring_verified_at": str(
                        company.get("security_hiring_verified_at") or ""
                    ),
                    "security_roles_verified": list(
                        company.get("security_roles_verified", [])
                    ),
                    "configured": True,
                }
            )
            employers[key] = entry

    base_hours = max(1, int(options.get("failure_cooldown_hours", 24)))
    max_hours = max(base_hours, int(options.get("max_failure_cooldown_hours", 168)))
    invalid_days = max(1, int(options.get("invalid_identifier_cooldown_days", 30)))

    for result in results:
        for company_result in getattr(result, "company_results", []):
            source = str(company_result.get("source") or result.source)
            identifier = str(company_result.get("identifier") or "")
            if not identifier:
                continue
            key = company_key(source, identifier)
            entry = dict(employers.get(key, {}))
            entry.update(
                {
                    "source": source,
                    "company": str(company_result.get("company") or identifier),
                    "identifier": identifier,
                    "last_checked_at": generated_at,
                    "jobs_last_seen": int(company_result.get("jobs") or 0),
                }
            )
            if company_result.get("status") == "ok":
                entry.update(
                    {
                        "status": "ok",
                        "consecutive_failures": 0,
                        "last_success_at": generated_at,
                        "last_http_status": None,
                        "last_error": "",
                        "next_retry_at": None,
                    }
                )
            else:
                failures = int(entry.get("consecutive_failures") or 0) + 1
                status = _status_code(company_result.get("http_status"))
                invalid = status in {404, 410}
                cooldown = (
                    timedelta(days=invalid_days)
                    if invalid
                    else timedelta(hours=min(max_hours, base_hours * (2 ** min(failures - 1, 8))))
                )
                entry.update(
                    {
                        "status": "invalid_identifier" if invalid else "temporarily_failed",
                        "consecutive_failures": failures,
                        "last_failure_at": generated_at,
                        "last_http_status": status,
                        "last_error": str(company_result.get("error") or "")[:300],
                        "next_retry_at": _format_time(now + cooldown),
                    }
                )
            employers[key] = entry

    for key, entry in employers.items():
        if key not in configured_keys:
            entry["configured"] = False

    ordered = {key: employers[key] for key in sorted(employers)}
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "scan": selection,
        "summary": {
            "configured": len(configured_keys),
            "healthy": sum(
                1 for key in configured_keys if ordered.get(key, {}).get("status") == "ok"
            ),
            "cooling_down": sum(
                1
                for key in configured_keys
                if _cooldown_active(ordered.get(key, {}).get("next_retry_at"), now)
            ),
            "invalid_identifiers": sum(
                1
                for key in configured_keys
                if ordered.get(key, {}).get("status") == "invalid_identifier"
            ),
        },
        "employers": ordered,
    }


def company_key(source: str, identifier: str) -> str:
    return f"{source.casefold()}:{identifier.strip().casefold()}"


def render_company_health_markdown(health: dict[str, Any]) -> str:
    summary = health.get("summary", {})
    scan = health.get("scan", {})
    employers = health.get("employers", {})
    lines = [
        "# Employer Watchlist Health",
        "",
        f"**Generated:** {health.get('generated_at', 'Unknown')}",
        f"**Scan mode:** {str(scan.get('mode', 'daily')).title()}",
        f"**Configured employers:** {summary.get('configured', 0)}",
        f"**Healthy after a completed check:** {summary.get('healthy', 0)}",
        f"**Cooling down:** {summary.get('cooling_down', 0)}",
        f"**Invalid identifiers:** {summary.get('invalid_identifiers', 0)}",
        "",
        "## Scan coverage",
        "",
    ]
    for source, details in scan.get("sources", {}).items():
        lines.append(
            f"- **{source.title()}:** {details.get('selected', 0)}/"
            f"{details.get('configured_enabled', 0)} selected; "
            f"{details.get('skipped_by_rotation', 0)} scheduled for another batch; "
            f"{details.get('skipped_by_cooldown', 0)} cooling down"
        )
    verified = [
        entry
        for entry in employers.values()
        if entry.get("configured")
        and entry.get("enabled")
        and entry.get("current_security_hiring")
    ]
    verified.sort(key=lambda entry: str(entry.get("company", "")).casefold())
    lines.extend(["", "## Verified security hiring watch", ""])
    if verified:
        for entry in verified:
            roles = ", ".join(entry.get("security_roles_verified", [])) or "Security role"
            lines.append(
                f"- **{entry.get('company')}:** {roles} "
                f"(verified {entry.get('security_hiring_verified_at') or 'date unknown'})"
            )
    else:
        lines.append("No employer is currently marked as verified security hiring.")
    problems = [
        entry
        for entry in employers.values()
        if entry.get("configured")
        and entry.get("status") in {"invalid_identifier", "temporarily_failed"}
    ]
    problems.sort(key=lambda entry: str(entry.get("company", "")).casefold())
    lines.extend(["", "## Suppressed or failing identifiers", ""])
    if problems:
        for entry in problems:
            lines.append(
                f"- **{entry.get('company')} ({entry.get('source')}):** "
                f"{entry.get('status')}; next retry {entry.get('next_retry_at') or 'next run'}; "
                f"{entry.get('last_error') or 'no detail'}"
            )
    else:
        lines.append("No configured employer is currently suppressed or failing.")
    lines.append("")
    return "\n".join(lines)


def _bucket(key: str, count: int) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % count


def _cooldown_active(value: Any, now: datetime) -> bool:
    if not value:
        return False
    try:
        return _parse_time(str(value)) > now
    except ValueError:
        return False


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_time(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _status_code(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _summary(
    source: str,
    mode: str,
    configured: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    rotation_skips: list[str],
    cooldown_skips: list[str],
    batch_index: int | None,
) -> dict[str, Any]:
    return {
        "source": source,
        "mode": mode,
        "batch_index": batch_index,
        "configured_enabled": len(configured),
        "priority_configured": sum(bool(company.get("priority", False)) for company in configured),
        "selected": len(selected),
        "skipped_by_rotation": len(rotation_skips),
        "skipped_by_cooldown": len(cooldown_skips),
        "rotation_skip_keys": rotation_skips,
        "cooldown_skip_keys": cooldown_skips,
    }
