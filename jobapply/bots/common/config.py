"""Layered bot configuration loaded from root env, JSON profiles, and runtime JSON."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

from bots import SUPPORTED_PLATFORMS
from .paths import APP_ROOT, ROOT_ENV_PATH, resolve_app_path, safe_named_json


load_dotenv(ROOT_ENV_PATH, override=False)


class ConfigError(ValueError):
    """Raised for actionable configuration errors before a browser is started."""


def deep_merge(*values: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings; later values win and lists are replaced."""

    merged: dict[str, Any] = {}
    for value in values:
        for key, incoming in value.items():
            if isinstance(incoming, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key] = deep_merge(merged[key], incoming)
            else:
                merged[key] = copy.deepcopy(incoming)
    return merged


def _json_object(raw: str | None, variable: str) -> dict[str, Any]:
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{variable} must contain valid JSON: {error.msg}") from error
    if not isinstance(parsed, dict):
        raise ConfigError(f"{variable} must contain a JSON object")
    return parsed


def _json_string_list(raw: str | None, variable: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError(f"{variable} must contain a JSON string array: {error.msg}") from error
    if not isinstance(parsed, list) or any(not isinstance(item, str) or not item.strip() for item in parsed):
        raise ConfigError(f"{variable} must contain a JSON array of non-empty strings")
    return [item.strip() for item in parsed]


def _read_json(path: Path, description: str, *, required: bool = True) -> dict[str, Any]:
    if not path.is_file():
        if required:
            raise ConfigError(f"Missing {description}: {path}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"Cannot read {description} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"{description.capitalize()} must be a JSON object: {path}")
    return value


def _bool(value: Any, name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false")


def _integer(value: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"{name} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return parsed


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConfigError(f"{name} must be a non-empty array of strings")
    return [item.strip() for item in value]


@dataclass(slots=True)
class AutomationConfig:
    platform: str
    filters: dict[str, Any]
    profile: dict[str, Any]
    headless: bool
    slow_mo: int
    max_applications: int
    applications_csv: Path
    filters_dir: Path
    max_pages: int = 3
    max_form_steps: int = 15
    browser: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def keywords(self) -> list[str]:
        return list(self.filters["keywords"])

    @property
    def locations(self) -> list[str]:
        return list(self.filters["locations"])

    def public_summary(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "headless": self.headless,
            "slowMo": self.slow_mo,
            "maxApplications": self.max_applications,
            "maxPages": self.max_pages,
            "applicationsCsv": str(self.applications_csv),
            "filtersDir": str(self.filters_dir),
            "keywords": self.keywords,
            "locations": self.locations,
        }


_RUNTIME_KEYS = {
    "platform",
    "filters",
    "headless",
    "slowMo",
    "slow_mo",
    "maxApplications",
    "max_applications",
    "applicationsCsv",
    "exportCsv",
    "profile",
    "profilePath",
    "filterOverrides",
    "browser",
    "maxPages",
    "maxFormSteps",
}


def load_config(
    platform: str,
    *,
    environ: Mapping[str, str] | None = None,
    app_root: Path = APP_ROOT,
    runtime_overrides: Mapping[str, Any] | None = None,
) -> AutomationConfig:
    """Load and validate one platform's complete, cwd-independent configuration."""

    if platform not in SUPPORTED_PLATFORMS:
        raise ConfigError(f"Unsupported platform {platform!r}; expected one of {', '.join(SUPPORTED_PLATFORMS)}")

    env = dict(os.environ if environ is None else environ)
    filters_dir = resolve_app_path(env.get("FILTERS_DIR"), "configs/filters", app_root=app_root)
    if not filters_dir.is_dir():
        raise ConfigError(f"FILTERS_DIR does not exist or is not a directory: {filters_dir}")

    legacy_runtime = _json_object(env.get("BOT_CONFIG"), "BOT_CONFIG")
    requested_runtime = _json_object(env.get("JOBAPPLY_BOT_CONFIG"), "JOBAPPLY_BOT_CONFIG")
    runtime = deep_merge(legacy_runtime, requested_runtime, runtime_overrides or {})
    runtime_platform = runtime.get("platform")
    if runtime_platform and runtime_platform not in {platform, "all"}:
        raise ConfigError(
            f"Runtime configuration targets {runtime_platform!r}, but {platform!r} was requested"
        )

    default_profile = _read_json(filters_dir / "default.json", "default filter profile")
    platform_profile = _read_json(filters_dir / f"{platform}.json", f"{platform} filter profile")
    declared_platform = platform_profile.get("platform")
    if declared_platform and declared_platform != platform:
        raise ConfigError(
            f"Filter profile {filters_dir / (platform + '.json')} declares platform {declared_platform!r}"
        )

    selected = runtime.get("filters")
    if selected is None:
        selected = _json_string_list(env.get("BOT_FILTERS") or env.get("FILTERS"), "BOT_FILTERS")
    elif not isinstance(selected, list) or any(not isinstance(item, str) or not item.strip() for item in selected):
        raise ConfigError("Runtime filters must be an array of non-empty profile names")

    merged_filters = deep_merge(default_profile, platform_profile)
    for profile_name in selected:
        try:
            profile_path = safe_named_json(filters_dir, profile_name.strip())
        except ValueError as error:
            raise ConfigError(str(error)) from error
        selected_profile = _read_json(profile_path, f"selected filter profile {profile_name!r}")
        selected_platform = selected_profile.get("platform")
        if selected_platform and selected_platform != platform:
            raise ConfigError(
                f"Selected filter profile {profile_name!r} targets {selected_platform!r}, not {platform!r}"
            )
        merged_filters = deep_merge(merged_filters, selected_profile)

    direct_filter_overrides = {
        key: value for key, value in runtime.items() if key not in _RUNTIME_KEYS
    }
    filter_overrides = runtime.get("filterOverrides", {})
    if not isinstance(filter_overrides, Mapping):
        raise ConfigError("filterOverrides must be a JSON object")
    merged_filters = deep_merge(merged_filters, direct_filter_overrides, filter_overrides)
    merged_filters["keywords"] = _string_list(merged_filters.get("keywords"), "keywords")
    merged_filters["locations"] = _string_list(merged_filters.get("locations"), "locations")

    profile: dict[str, Any] = {}
    configured_profile_path = env.get("PROFILE_PATH") or runtime.get("profilePath")
    conventional_profile_path = app_root / "configs" / "profile.json"
    if configured_profile_path:
        path = resolve_app_path(str(configured_profile_path), "configs/profile.json", app_root=app_root)
        profile = _read_json(path, "candidate profile")
    elif conventional_profile_path.is_file():
        profile = _read_json(conventional_profile_path, "candidate profile")
    embedded_profile = runtime.get("profile", {})
    if not isinstance(embedded_profile, Mapping):
        raise ConfigError("profile must be a JSON object")
    profile = deep_merge(merged_filters.get("profile", {}), profile, embedded_profile)

    headless_source = env["HEADLESS"] if "HEADLESS" in env else runtime.get("headless", merged_filters.get("headless"))
    slow_source = env["SLOW_MO"] if "SLOW_MO" in env else runtime.get("slowMo", runtime.get("slow_mo", merged_filters.get("slowMo")))
    max_source = env["MAX_APPLICATIONS"] if "MAX_APPLICATIONS" in env else runtime.get(
        "maxApplications", runtime.get("max_applications", merged_filters.get("maxApplications"))
    )
    csv_source = env.get("APPLICATIONS_CSV") or runtime.get("applicationsCsv")

    browser = merged_filters.get("browser", {})
    runtime_browser = runtime.get("browser", {})
    if not isinstance(browser, Mapping) or not isinstance(runtime_browser, Mapping):
        raise ConfigError("browser configuration must be a JSON object")

    return AutomationConfig(
        platform=platform,
        filters=merged_filters,
        profile=profile,
        headless=_bool(headless_source, "HEADLESS", False),
        slow_mo=_integer(slow_source, "SLOW_MO", 250, 0, 60_000),
        max_applications=_integer(max_source, "MAX_APPLICATIONS", 25, 1, 10_000),
        applications_csv=resolve_app_path(csv_source, "logs/applications.csv", app_root=app_root),
        filters_dir=filters_dir,
        max_pages=_integer(runtime.get("maxPages", merged_filters.get("maxPages")), "maxPages", 3, 1, 100),
        max_form_steps=_integer(
            runtime.get("maxFormSteps", merged_filters.get("maxFormSteps")),
            "maxFormSteps",
            15,
            1,
            50,
        ),
        browser=deep_merge(browser, runtime_browser),
        runtime=runtime,
    )
