from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class ConfigError(ValueError):
    """Local browser configuration is missing or unsafe."""


PLACEHOLDER_LVMS_HOSTS = frozenset(
    {"lvms.example.invalid", "lvms.sykehus.no"}
)


def is_placeholder_landing_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        hostname = urlsplit(value.strip()).hostname
    except ValueError:
        return False
    return bool(hostname and hostname.lower() in PLACEHOLDER_LVMS_HOSTS)


@dataclass(frozen=True)
class BrowserConfig:
    landing_url: str
    expected_origin: str
    profile_directory: Path


@dataclass(frozen=True)
class AppConfig(BrowserConfig):
    download_directory: Path


def _required_text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty string")
    return value.strip()


def validate_config(
    raw: Mapping[str, object],
    *,
    repository_root: Path,
    allowed_profile_root: Path | None = None,
) -> BrowserConfig:
    landing_url = _required_text(raw, "landing_url")
    parsed = urlsplit(landing_url)

    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConfigError("landing_url has an invalid host or port") from exc

    if parsed.scheme != "https" or not hostname:
        raise ConfigError("landing_url must be an HTTPS URL")
    if is_placeholder_landing_url(landing_url):
        raise ConfigError(
            "Oppsett: erstatt eksempeladressen med den faktiske LVMS-adressen"
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError(
            "landing_url must not contain credentials, query, or fragment"
        )

    profile_text = _required_text(raw, "profile_directory")
    profile_candidate = Path(profile_text).expanduser()
    if not profile_candidate.is_absolute():
        raise ConfigError("profile_directory must be an absolute path")
    profile_directory = profile_candidate.resolve()
    resolved_repository = repository_root.resolve()
    if (
        profile_directory == resolved_repository
        or resolved_repository in profile_directory.parents
    ):
        raise ConfigError("profile_directory must be outside the repository")

    if allowed_profile_root is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise ConfigError("local application-data directory is unavailable")
        allowed_profile_root = Path(local_app_data)
    resolved_profile_root = allowed_profile_root.expanduser().resolve()
    if (
        profile_directory == resolved_profile_root
        or resolved_profile_root not in profile_directory.parents
    ):
        raise ConfigError(
            "profile_directory must be beneath the local application-data directory"
        )

    host_and_port = hostname if port is None else f"{hostname}:{port}"
    expected_origin = f"https://{host_and_port}"
    configured_origin = raw.get("expected_origin")
    if configured_origin is not None:
        if not isinstance(configured_origin, str) or configured_origin != expected_origin:
            raise ConfigError("expected_origin must exactly match the landing URL origin")
    return BrowserConfig(
        landing_url=landing_url,
        expected_origin=expected_origin,
        profile_directory=profile_directory,
    )


def _local_root(candidate: Path | None) -> Path:
    if candidate is None:
        text = os.environ.get("LOCALAPPDATA")
        if not text:
            raise ConfigError("local application-data directory is unavailable")
        candidate = Path(text)
    return candidate.expanduser().resolve()


def _external_directory(
    raw: Mapping[str, object], key: str, repository_root: Path
) -> Path:
    candidate = Path(_required_text(raw, key)).expanduser()
    if not candidate.is_absolute():
        raise ConfigError(f"{key} must be an absolute path")
    resolved = candidate.resolve()
    repository = repository_root.resolve()
    if resolved == repository or repository in resolved.parents:
        raise ConfigError(f"{key} must be outside the repository")
    return resolved


def validate_app_config(
    raw: Mapping[str, object],
    *,
    repository_root: Path,
    allowed_local_root: Path | None = None,
) -> AppConfig:
    local = _local_root(allowed_local_root)
    browser = validate_config(
        raw,
        repository_root=repository_root,
        allowed_profile_root=local,
    )
    downloads = _external_directory(raw, "download_directory", repository_root)
    if downloads == local or local not in downloads.parents:
        raise ConfigError("download_directory must be beneath local application data")
    return AppConfig(
        landing_url=browser.landing_url,
        expected_origin=browser.expected_origin,
        profile_directory=browser.profile_directory,
        download_directory=downloads,
    )


def load_app_config(
    path: Path,
    *,
    repository_root: Path,
    allowed_local_root: Path | None = None,
) -> AppConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError("configuration file could not be read") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError("configuration file is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise ConfigError("configuration must contain a JSON object")
    return validate_app_config(
        raw,
        repository_root=repository_root,
        allowed_local_root=allowed_local_root,
    )

