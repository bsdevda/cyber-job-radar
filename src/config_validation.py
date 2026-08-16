from __future__ import annotations

from datetime import date
from typing import Any

from .utils import normalize_text


ATS_IDENTIFIERS = {
    "greenhouse": "board",
    "lever": "site",
    "ashby": "board",
    "personio": "account",
    "recruitee": "subdomain",
    "smartrecruiters": "identifier",
}
ALLOWED_COMPANY_KEYS = {"priority_companies", "notes", *ATS_IDENTIFIERS}


class ConfigurationError(ValueError):
    """Raised when a user-editable configuration file is structurally invalid."""


def validate_companies_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ConfigurationError("config/companies.json must contain a JSON object")

    unknown = sorted(set(config) - ALLOWED_COMPANY_KEYS)
    if unknown:
        raise ConfigurationError(
            "Unsupported companies.json section(s): " + ", ".join(unknown)
        )

    priority_companies = config.get("priority_companies", [])
    if not isinstance(priority_companies, list) or not all(
        isinstance(name, str) and name.strip() for name in priority_companies
    ):
        raise ConfigurationError("priority_companies must be a list of non-empty strings")
    if "notes" in config and not isinstance(config["notes"], str):
        raise ConfigurationError("companies.json notes must be a string")

    for ats, identifier_field in ATS_IDENTIFIERS.items():
        entries = config.get(ats, [])
        if not isinstance(entries, list):
            raise ConfigurationError(f"companies.json '{ats}' must be a list")
        identifiers: set[str] = set()
        names: set[str] = set()
        for index, entry in enumerate(entries):
            label = f"{ats}[{index}]"
            if not isinstance(entry, dict):
                raise ConfigurationError(f"{label} must be a JSON object")
            for boolean_field in ("enabled", "priority", "current_security_hiring"):
                if boolean_field in entry and not isinstance(entry[boolean_field], bool):
                    raise ConfigurationError(f"{label}.{boolean_field} must be true or false")
            if "notes" in entry and not isinstance(entry["notes"], str):
                raise ConfigurationError(f"{label}.notes must be a string")
            if "category" in entry and (
                not isinstance(entry["category"], str) or not entry["category"].strip()
            ):
                raise ConfigurationError(f"{label}.category must be a non-empty string")
            roles = entry.get("security_roles_verified", [])
            if not isinstance(roles, list) or not all(
                isinstance(role, str) and role.strip() for role in roles
            ):
                raise ConfigurationError(
                    f"{label}.security_roles_verified must be a list of non-empty strings"
                )
            verified_at = entry.get("security_hiring_verified_at")
            if verified_at is not None:
                if not isinstance(verified_at, str):
                    raise ConfigurationError(
                        f"{label}.security_hiring_verified_at must use YYYY-MM-DD"
                    )
                try:
                    date.fromisoformat(verified_at)
                except ValueError as exc:
                    raise ConfigurationError(
                        f"{label}.security_hiring_verified_at must use YYYY-MM-DD"
                    ) from exc
            if ats == "lever" and entry.get("region", "global") not in {"global", "eu"}:
                raise ConfigurationError(f"{label}.region must be 'global' or 'eu'")
            if ats == "personio" and entry.get("language", "en") not in {
                "de", "en", "fr", "es", "nl", "it", "pt"
            }:
                raise ConfigurationError(f"{label}.language is not supported by Personio")
            name = entry.get("name")
            identifier = entry.get(identifier_field)
            if not isinstance(name, str) or not name.strip():
                raise ConfigurationError(f"{label}.name is required and must be a non-empty string")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ConfigurationError(
                    f"{label}.{identifier_field} is required and must be a non-empty string"
                )
            normalized_identifier = identifier.strip().casefold()
            normalized_name = normalize_text(name)
            if normalized_identifier in identifiers:
                raise ConfigurationError(
                    f"Duplicate {ats} {identifier_field} '{identifier}' in companies.json"
                )
            if normalized_name in names:
                raise ConfigurationError(f"Duplicate {ats} company name '{name}' in companies.json")
            identifiers.add(normalized_identifier)
            names.add(normalized_name)
    return config


def priority_company_names(config: dict[str, Any]) -> set[str]:
    names = {normalize_text(name) for name in config.get("priority_companies", [])}
    for ats in ATS_IDENTIFIERS:
        for company in config.get(ats, []):
            if company.get("enabled", True) and company.get("priority", False):
                names.add(normalize_text(str(company["name"])))
    return names
