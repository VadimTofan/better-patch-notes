from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from automation.models import RegisteredSource, SourceRegistry


REGISTRY_FIELDS = {
    "schemaVersion",
    "allowedHosts",
    "blueAuthors",
    "maxResponseBytes",
    "timeoutSeconds",
    "sources",
}
SOURCE_FIELDS = {
    "url",
    "kind",
    "channel",
    "patch",
    "locale",
    "titlePatterns",
}
SOURCE_KINDS = {"news_feed", "forum_category", "forum_topic", "version"}
CHANNELS = {"live", "ptr"}
LOCALES = {
    "deDE",
    "en",
    "esES",
    "esMX",
    "frFR",
    "itIT",
    "koKR",
    "ptBR",
    "ruRU",
    "zhCN",
    "zhTW",
}


def _require_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")

    return value


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")

    return value.strip()


def _require_positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")

    return value


def _require_string_list(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")

    values = tuple(_require_string(item, name) for item in value)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates")

    return values


def _is_official_host(host: str) -> bool:
    return host == "blizzard.com" or host.endswith(".blizzard.com") or (
        host == "battle.net" or host.endswith(".battle.net")
    )


def _validate_host(host: str) -> str:
    normalized = host.lower().rstrip(".")
    if not _is_official_host(normalized):
        raise ValueError(f"unsupported Blizzard host: {host}")

    return normalized


def _load_source(
    value: object,
    allowed_hosts: frozenset[str],
) -> RegisteredSource:
    source = _require_object(value, "source")
    unknown_fields = set(source) - SOURCE_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"unknown source fields: {fields}")

    url = _require_string(source.get("url"), "source url")
    parsed_url = urlsplit(url)
    host = (parsed_url.hostname or "").lower().rstrip(".")
    if parsed_url.scheme != "https" or host not in allowed_hosts:
        raise ValueError(f"source URL is not allowlisted: {url}")
    if parsed_url.username or parsed_url.password:
        raise ValueError("source URL must not contain credentials")

    kind = _require_string(source.get("kind"), "source kind")
    if kind not in SOURCE_KINDS:
        raise ValueError(f"unsupported source kind: {kind}")

    channel = _require_string(source.get("channel"), "source channel")
    if channel not in CHANNELS:
        raise ValueError(f"unsupported source channel: {channel}")

    patch = _require_string(source.get("patch"), "source patch")
    patch_parts = patch.split(".")
    if patch != "current" and (
        len(patch_parts) != 3
        or any(not part.isdigit() for part in patch_parts)
    ):
        raise ValueError(f"unsupported source patch: {patch}")
    if channel == "ptr" and patch == "current":
        raise ValueError("PTR source patch must be numeric")

    locale = _require_string(source.get("locale"), "source locale")
    if locale not in LOCALES:
        raise ValueError(f"unsupported source locale: {locale}")

    title_patterns = _require_string_list(
        source.get("titlePatterns"),
        "source titlePatterns",
    )

    return RegisteredSource(
        url=url,
        kind=kind,
        channel=channel,
        patch=patch,
        locale=locale,
        title_patterns=title_patterns,
    )


def load_registry(path: Path) -> SourceRegistry:
    document = _require_object(
        json.loads(path.read_text(encoding="utf-8")),
        "registry",
    )
    unknown_fields = set(document) - REGISTRY_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"unknown registry fields: {fields}")
    if document.get("schemaVersion") != 1:
        raise ValueError("schemaVersion must be 1")

    allowed_hosts = frozenset(
        _validate_host(host)
        for host in _require_string_list(
            document.get("allowedHosts"),
            "allowedHosts",
        )
    )
    blue_authors = frozenset(
        _require_string_list(document.get("blueAuthors"), "blueAuthors")
    )
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("sources must be a non-empty list")

    sources = tuple(
        _load_source(source, allowed_hosts) for source in raw_sources
    )

    return SourceRegistry(
        allowed_hosts=allowed_hosts,
        blue_authors=blue_authors,
        max_response_bytes=_require_positive_integer(
            document.get("maxResponseBytes"),
            "maxResponseBytes",
        ),
        timeout_seconds=_require_positive_integer(
            document.get("timeoutSeconds"),
            "timeoutSeconds",
        ),
        sources=sources,
    )
