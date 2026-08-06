from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from generate_lua_data import render_lua_data
from update_data import _validate_batch, update_data


PROJECT_ROOT = SCRIPT_DIRECTORY.parents[2]
DEFAULT_BUILD_INFO_PATH = PROJECT_ROOT.parents[3] / ".build.info"


@dataclass(frozen=True, slots=True)
class RefreshResult:
    added: int
    skipped: int
    promoted: int
    localized: int
    ambiguous: int
    removed: int


def _patch_tuple(version: str) -> tuple[int, int, int]:
    parts = version.split(".")
    if len(parts) < 2 or len(parts) > 4:
        raise ValueError(f"invalid patch version: {version}")
    if any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid patch version: {version}")

    numbers = [int(part) for part in parts[:3]]
    while len(numbers) < 3:
        numbers.append(0)

    return tuple(numbers)


def detect_game_patch(build_info_path: Path) -> str:
    with build_info_path.open(encoding="utf-8", newline="") as build_file:
        rows = csv.reader(build_file, delimiter="|")
        header = next(rows, None)
        if header is None:
            raise ValueError(".build.info is empty")

        field_names = [field.split("!", 1)[0] for field in header]
        for row in rows:
            build = dict(zip(field_names, row, strict=False))
            if build.get("Active") != "1" or build.get("Product") != "wow":
                continue

            version = build.get("Version", "")
            major, minor, patch = _patch_tuple(version)

            return f"{major}.{minor}.{patch}"

    raise ValueError("active Retail build is missing from .build.info")


def retain_relevant_changes(
    document: dict[str, object],
    game_version: str,
    as_of_date: str,
) -> tuple[dict[str, object], int]:
    current_patch = _patch_tuple(game_version)
    retention_date = date.fromisoformat(as_of_date)
    cutoff_date = retention_date - timedelta(days=13)
    raw_changes = document.get("changes")
    if not isinstance(raw_changes, list):
        raise ValueError("changes must be a list")

    retained_changes: list[object] = []
    for raw_change in raw_changes:
        if not isinstance(raw_change, dict):
            raise ValueError("each change must be an object")

        try:
            patch = _patch_tuple(str(raw_change.get("patch", "")))
            change_date = date.fromisoformat(
                str(raw_change.get("date", ""))
            )
        except ValueError:
            continue

        channel = raw_change.get("channel")
        is_relevant = (
            channel == "live" and patch == current_patch
        ) or (
            channel == "ptr" and patch > current_patch
        )
        if is_relevant and cutoff_date <= change_date <= retention_date:
            retained_changes.append(raw_change)

    retained_document = dict(document)
    retained_document["changes"] = retained_changes
    removed = len(raw_changes) - len(retained_changes)

    return retained_document, removed


def _write_temporary_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=path.parent,
        suffix=f"{path.suffix}.tmp",
    ) as temporary_file:
        temporary_file.write(content)

        return Path(temporary_file.name)


def _restore_file(path: Path, previous_content: bytes | None) -> None:
    if previous_content is None:
        if path.exists():
            path.unlink()
        return

    with NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=path.parent,
        suffix=f"{path.suffix}.restore.tmp",
    ) as temporary_file:
        temporary_file.write(previous_content)
        temporary_path = Path(temporary_file.name)

    os.replace(temporary_path, path)


def _publish_pair(
    data_path: Path,
    data_content: str,
    lua_path: Path,
    lua_content: str,
) -> None:
    previous_data = data_path.read_bytes() if data_path.exists() else None
    previous_lua = lua_path.read_bytes() if lua_path.exists() else None
    temporary_data = _write_temporary_file(data_path, data_content)
    temporary_lua = _write_temporary_file(lua_path, lua_content)

    try:
        os.replace(temporary_data, data_path)
        os.replace(temporary_lua, lua_path)
    except OSError:
        _restore_file(data_path, previous_data)
        _restore_file(lua_path, previous_lua)
        raise
    finally:
        if temporary_data.exists():
            temporary_data.unlink()
        if temporary_lua.exists():
            temporary_lua.unlink()


def refresh_patch_notes(
    input_path: Path,
    data_path: Path,
    lua_path: Path,
    game_version: str | None = None,
) -> RefreshResult:
    resolved_game_version = game_version or detect_game_patch(
        DEFAULT_BUILD_INFO_PATH
    )
    batch = json.loads(input_path.read_text(encoding="utf-8"))
    retrieved_at, incoming_changes = _validate_batch(batch)

    with TemporaryDirectory() as temporary_directory:
        staged_data_path = (
            Path(temporary_directory) / "retail-patch-notes.json"
        )
        if data_path.exists():
            shutil.copyfile(data_path, staged_data_path)

        result = update_data(
            staged_data_path,
            incoming_changes,
            retrieved_at,
        )
        staged_document = json.loads(
            staged_data_path.read_text(encoding="utf-8")
        )
        staged_document, removed = retain_relevant_changes(
            staged_document,
            resolved_game_version,
            datetime.fromisoformat(retrieved_at).date().isoformat(),
        )
        if removed:
            staged_document["updatedAt"] = retrieved_at
        lua_content = render_lua_data(staged_document)
        data_content = json.dumps(
            staged_document,
            ensure_ascii=False,
            indent=2,
        ) + "\n"

    _publish_pair(data_path, data_content, lua_path, lua_content)

    return RefreshResult(
        added=result.added,
        skipped=result.skipped,
        promoted=result.promoted,
        localized=result.localized,
        ambiguous=result.ambiguous,
        removed=removed,
    )


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update canonical patch-note JSON and generated WoW Lua.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--lua-output", required=True, type=Path)
    parser.add_argument("--game-version")

    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    try:
        result = refresh_patch_notes(
            arguments.input,
            arguments.data,
            arguments.lua_output,
            arguments.game_version,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Refresh failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
