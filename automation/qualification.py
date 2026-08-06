from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import date, timedelta
from io import StringIO

from automation.models import ExtractedChange


SUPPORTED_CATEGORIES = {"Class", "Dungeon", "Raid"}


@dataclass(frozen=True, slots=True)
class RejectedChange:
    change: ExtractedChange
    reason: str


@dataclass(frozen=True, slots=True)
class QualificationResult:
    accepted: tuple[ExtractedChange, ...]
    rejected: tuple[RejectedChange, ...]


def _patch_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) < 2 or len(parts) > 4:
        raise ValueError(f"invalid patch version: {version}")
    if any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid patch version: {version}")

    values = [int(part) for part in parts[:3]]
    while len(values) < 3:
        values.append(0)

    return tuple(values)


def _patch_name(version: str) -> str:
    major, minor, patch = _patch_tuple(version)
    return f"{major}.{minor}.{patch}"


def _parse_product_versions(body: bytes) -> dict[str, str]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("product versions are not UTF-8") from error

    lines = [
        line for line in text.splitlines() if line and not line.startswith("##")
    ]
    if len(lines) < 2:
        raise ValueError("product versions response is empty")

    reader = csv.reader(StringIO("\n".join(lines)), delimiter="|")
    header = next(reader)
    fields = [field.split("!", 1)[0] for field in header]
    if "Region" not in fields or "VersionsName" not in fields:
        raise ValueError("product versions response has unknown fields")

    versions: dict[str, str] = {}
    for row in reader:
        values = dict(zip(fields, row, strict=False))
        region = values.get("Region", "").strip().lower()
        version = values.get("VersionsName", "").strip()
        if region and version:
            versions[region] = _patch_name(version)

    return versions


def resolve_retail_patch(
    responses: tuple[bytes, ...],
    required_regions: tuple[str, ...] = ("us", "eu"),
) -> str:
    if not responses:
        raise ValueError("at least one product version response is required")

    observed: set[str] = set()
    for response in responses:
        versions = _parse_product_versions(response)
        for region in required_regions:
            if region not in versions:
                raise ValueError(f"product versions are missing region: {region}")
            observed.add(versions[region])

    if len(observed) != 1:
        raise ValueError("Retail version responses disagree")

    return observed.pop()


def qualify(
    changes: tuple[ExtractedChange, ...],
    current_patch: str,
    as_of_date: date,
) -> QualificationResult:
    current_patch_tuple = _patch_tuple(current_patch)
    cutoff = as_of_date - timedelta(days=13)
    accepted: list[ExtractedChange] = []
    rejected: list[RejectedChange] = []

    for change in changes:
        reason = ""
        if change.category not in SUPPORTED_CATEGORIES:
            reason = "unsupported category"
        elif change.effective_date > as_of_date:
            reason = "effective date is in the future"
        elif change.effective_date < cutoff:
            reason = "outside rolling 14-day window"
        else:
            resolved_patch = (
                current_patch if change.patch == "current" else change.patch
            )
            try:
                candidate_patch = _patch_tuple(resolved_patch)
            except ValueError:
                reason = "invalid patch version"
            else:
                if change.channel == "live" and (
                    candidate_patch != current_patch_tuple
                ):
                    reason = "live patch mismatch"
                elif change.channel == "ptr" and (
                    candidate_patch <= current_patch_tuple
                ):
                    reason = "PTR patch is not newer"
                elif change.channel not in {"live", "ptr"}:
                    reason = "unsupported channel"
                else:
                    accepted.append(
                        replace(change, patch=_patch_name(resolved_patch))
                    )

        if reason:
            rejected.append(RejectedChange(change=change, reason=reason))

    return QualificationResult(
        accepted=tuple(accepted),
        rejected=tuple(rejected),
    )
