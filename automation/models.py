from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class RefreshStatus(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    BLOCKED = "BLOCKED"
    RELEASE_READY = "RELEASE_READY"


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    url: str
    kind: str
    channel: str
    patch: str
    locale: str
    title_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceRegistry:
    allowed_hosts: frozenset[str]
    blue_authors: frozenset[str]
    max_response_bytes: int
    timeout_seconds: int
    sources: tuple[RegisteredSource, ...]


@dataclass(frozen=True, slots=True)
class HttpResponse:
    body: bytes
    final_url: str
    mime_type: str
    status: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class SourceDocument:
    url: str
    channel: str
    patch: str
    locale: str
    title: str
    author: str
    published_at: datetime
    updated_at: datetime | None
    body: bytes
    mime_type: str
    content_hash: str
    author_is_blue: bool


@dataclass(frozen=True, slots=True)
class ExtractedChange:
    channel: str
    category: str
    effective_date: date
    patch: str
    name: str
    specialization: str
    change: tuple[str, ...]
    source_url: str


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    status: RefreshStatus
    added: int = 0
    updated: int = 0
    removed: int = 0
    version: str = ""
    reason: str = ""
    terminology_warnings: tuple[str, ...] = ()
