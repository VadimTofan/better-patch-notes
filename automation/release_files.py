from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import re


@dataclass(frozen=True, slots=True)
class ReleaseFiles:
    toc: Path
    addon: Path
    readme: Path
    changelog: Path
    data: Path
    lua: Path

    def paths(self) -> tuple[Path, ...]:
        return (
            self.toc,
            self.addon,
            self.readme,
            self.changelog,
            self.data,
            self.lua,
        )


@dataclass(frozen=True, slots=True)
class ReleaseSummary:
    live_patch: str
    ptr_patch: str
    added: int
    updated: int
    removed: int
    locale_text: str


def _meaningful_document(document: dict[str, object]) -> dict[str, object]:
    meaningful = deepcopy(document)
    meaningful.pop("updatedAt", None)

    return meaningful


def has_meaningful_change(
    before: dict[str, object],
    after: dict[str, object],
) -> bool:
    return json.dumps(
        _meaningful_document(before),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) != json.dumps(
        _meaningful_document(after),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def snapshot_files(files: ReleaseFiles) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in files.paths()}


def restore_snapshot(snapshot: dict[Path, bytes]) -> None:
    for path, content in snapshot.items():
        path.write_bytes(content)


def _extract_version(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8-sig"), re.MULTILINE)
    if match is None:
        raise ValueError(f"release version is missing from {path.name}")

    return match.group(1)


def read_versions(files: ReleaseFiles) -> set[str]:
    return {
        _extract_version(
            files.toc,
            r"^## Version: (\d+\.\d+\.\d+)$",
        ),
        _extract_version(
            files.addon,
            r'^addon\.version = "(\d+\.\d+\.\d+)"$',
        ),
        _extract_version(
            files.readme,
            r"^- \*\*Addon version:\*\* (\d+\.\d+\.\d+)$",
        ),
        _extract_version(
            files.changelog,
            r"^Version (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}$",
        ),
    }


def _bump_patch(version: str) -> str:
    major, minor, patch = (int(value) for value in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    updated, count = re.subn(
        pattern,
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise ValueError(f"unable to update release version in {path.name}")
    path.write_text(updated, encoding="utf-8", newline="")


def update_release_files(
    files: ReleaseFiles,
    release_date: date,
    summary: ReleaseSummary,
) -> str:
    versions = read_versions(files)
    if len(versions) != 1:
        raise ValueError("release versions are not synchronized")

    old_version = next(iter(versions))
    new_version = _bump_patch(old_version)
    _replace_once(
        files.toc,
        r"^## Version: \d+\.\d+\.\d+$",
        f"## Version: {new_version}",
    )
    _replace_once(
        files.addon,
        r'^addon\.version = "\d+\.\d+\.\d+"$',
        f'addon.version = "{new_version}"',
    )
    _replace_once(
        files.readme,
        r"^- \*\*Addon version:\*\* \d+\.\d+\.\d+$",
        f"- **Addon version:** {new_version}",
    )

    removed_text = (
        "None" if summary.removed == 0 else f"{summary.removed} stale records"
    )
    entry = (
        f"Version {new_version} - {release_date.isoformat()}\n"
        f"- Data: Live {summary.live_patch}; PTR {summary.ptr_patch}\n"
        "- Added or updated: "
        f"{summary.added} added; {summary.updated} updated\n"
        f"- Removed: {removed_text}\n"
        f"- Locales: {summary.locale_text}\n\n"
    )
    previous_changelog = files.changelog.read_text(encoding="utf-8-sig")
    files.changelog.write_text(
        entry + previous_changelog,
        encoding="utf-8",
        newline="",
    )

    synchronized_versions = read_versions(files)
    if synchronized_versions != {new_version}:
        raise ValueError("release versions are not synchronized after update")

    return new_version
