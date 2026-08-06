from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys


SCHEMA_VERSION = 5
VALID_CHANNELS = ("live", "ptr")
LUA_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CLASS_TOKENS = {
    "Death Knight": "DEATHKNIGHT",
    "Demon Hunter": "DEMONHUNTER",
    "Druid": "DRUID",
    "Evoker": "EVOKER",
    "Hunter": "HUNTER",
    "Mage": "MAGE",
    "Monk": "MONK",
    "Paladin": "PALADIN",
    "Priest": "PRIEST",
    "Rogue": "ROGUE",
    "Shaman": "SHAMAN",
    "Warlock": "WARLOCK",
    "Warrior": "WARRIOR",
}

SPECIALIZATION_IDS = {
    ("Death Knight", "Blood"): 250,
    ("Death Knight", "Frost"): 251,
    ("Death Knight", "Unholy"): 252,
    ("Demon Hunter", "Havoc"): 577,
    ("Demon Hunter", "Vengeance"): 581,
    ("Demon Hunter", "Devourer"): 1480,
    ("Druid", "Balance"): 102,
    ("Druid", "Feral"): 103,
    ("Druid", "Guardian"): 104,
    ("Druid", "Restoration"): 105,
    ("Evoker", "Devastation"): 1467,
    ("Evoker", "Preservation"): 1468,
    ("Evoker", "Augmentation"): 1473,
    ("Hunter", "Beast Mastery"): 253,
    ("Hunter", "Marksmanship"): 254,
    ("Hunter", "Survival"): 255,
    ("Mage", "Arcane"): 62,
    ("Mage", "Fire"): 63,
    ("Mage", "Frost"): 64,
    ("Monk", "Brewmaster"): 268,
    ("Monk", "Windwalker"): 269,
    ("Monk", "Mistweaver"): 270,
    ("Paladin", "Holy"): 65,
    ("Paladin", "Protection"): 66,
    ("Paladin", "Retribution"): 70,
    ("Priest", "Discipline"): 256,
    ("Priest", "Holy"): 257,
    ("Priest", "Shadow"): 258,
    ("Rogue", "Assassination"): 259,
    ("Rogue", "Outlaw"): 260,
    ("Rogue", "Subtlety"): 261,
    ("Shaman", "Elemental"): 262,
    ("Shaman", "Enhancement"): 263,
    ("Shaman", "Restoration"): 264,
    ("Warlock", "Affliction"): 265,
    ("Warlock", "Demonology"): 266,
    ("Warlock", "Destruction"): 267,
    ("Warrior", "Arms"): 71,
    ("Warrior", "Fury"): 72,
    ("Warrior", "Protection"): 73,
}


def _require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")

    return value


def _require_string(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")

    return value


def _runtime_identifiers(change: dict[str, object]) -> tuple[str, int]:
    if change.get("category") != "Class":
        return "", 0

    localizations = _require_dict(change.get("localizations"), "localizations")
    english = _require_dict(localizations.get("en"), "en localization")
    class_name = _require_string(english, "name")
    specialization = _require_string(english, "specialization")
    class_token = CLASS_TOKENS.get(class_name)
    if class_token is None:
        raise ValueError(f"unknown class: {class_name}")

    if specialization in {"", "All"}:
        return class_token, 0

    specialization_id = SPECIALIZATION_IDS.get(
        (class_name, specialization)
    )
    if specialization_id is None:
        raise ValueError(
            f"unknown specialization: {class_name} {specialization}"
        )

    return class_token, specialization_id


def _prepare_document(document: object) -> dict[str, object]:
    source = _require_dict(document, "canonical data")
    if source.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schemaVersion: {source.get('schemaVersion')}"
        )

    updated_at = _require_string(source, "updatedAt")
    changes = source.get("changes")
    if not isinstance(changes, list):
        raise ValueError("changes must be a list")

    prepared_changes: list[dict[str, object]] = []
    changes_by_channel: dict[str, list[dict[str, object]]] = {
        channel: [] for channel in VALID_CHANNELS
    }
    for raw_change in changes:
        change = dict(_require_dict(raw_change, "each change"))
        channel = _require_string(change, "channel")
        if channel not in changes_by_channel:
            raise ValueError(f"unsupported channel: {channel}")

        class_token, specialization_id = _runtime_identifiers(change)
        change["classToken"] = class_token
        change["specializationId"] = specialization_id
        prepared_changes.append(change)
        changes_by_channel[channel].append(change)

    channel_versions: dict[str, str] = {}
    latest_dates: dict[str, str] = {}
    record_counts: dict[str, int] = {}
    for channel in VALID_CHANNELS:
        channel_changes = changes_by_channel[channel]
        canonical_channel = json.dumps(
            sorted(channel_changes, key=lambda item: str(item.get("id", ""))),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        channel_versions[channel] = sha256(canonical_channel).hexdigest()[:16]
        latest_dates[channel] = max(
            (str(change.get("date", "")) for change in channel_changes),
            default="",
        )
        record_counts[channel] = len(channel_changes)

    class_channel_versions: dict[str, dict[str, str]] = {}
    class_latest_dates: dict[str, dict[str, str]] = {}
    for class_token in sorted(CLASS_TOKENS.values()):
        class_channel_versions[class_token] = {}
        class_latest_dates[class_token] = {}
        for channel in VALID_CHANNELS:
            relevant_changes = [
                change
                for change in changes_by_channel[channel]
                if change["category"] != "Class"
                or change["classToken"] == class_token
            ]
            if relevant_changes:
                canonical_relevant = json.dumps(
                    sorted(
                        relevant_changes,
                        key=lambda item: str(item.get("id", "")),
                    ),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                version = sha256(canonical_relevant).hexdigest()[:16]
            else:
                version = ""

            class_channel_versions[class_token][channel] = version
            class_latest_dates[class_token][channel] = max(
                (
                    str(change.get("date", ""))
                    for change in relevant_changes
                ),
                default="",
            )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": updated_at,
        "channelVersions": channel_versions,
        "classChannelVersions": class_channel_versions,
        "classLatestDates": class_latest_dates,
        "latestDates": latest_dates,
        "recordCounts": record_counts,
        "changes": prepared_changes,
    }


def _quote_lua(value: str) -> str:
    pieces: list[str] = ['"']
    for character in value:
        if character == "\\":
            pieces.append("\\\\")
        elif character == '"':
            pieces.append('\\"')
        elif character == "\n":
            pieces.append("\\n")
        elif character == "\r":
            pieces.append("\\r")
        elif character == "\t":
            pieces.append("\\t")
        elif ord(character) < 32:
            pieces.append(f"\\{ord(character):03d}")
        else:
            pieces.append(character)
    pieces.append('"')

    return "".join(pieces)


def _render_key(key: object) -> str:
    if isinstance(key, str) and LUA_IDENTIFIER_PATTERN.fullmatch(key):
        return key

    return f"[{_render_lua(key, 0)}]"


def _render_lua(value: object, indentation: int) -> str:
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return _quote_lua(value)

    current_indent = " " * indentation
    child_indent = " " * (indentation + 4)
    if isinstance(value, list):
        if not value:
            return "{}"
        lines = ["{"]
        for item in value:
            rendered = _render_lua(item, indentation + 4)
            lines.append(f"{child_indent}{rendered},")
        lines.append(f"{current_indent}}}")

        return "\n".join(lines)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for key in sorted(value, key=lambda item: str(item)):
            rendered = _render_lua(value[key], indentation + 4)
            lines.append(
                f"{child_indent}{_render_key(key)} = {rendered},"
            )
        lines.append(f"{current_indent}}}")

        return "\n".join(lines)

    raise ValueError(f"unsupported Lua value: {type(value).__name__}")


def render_lua_data(document: object) -> str:
    prepared_document = _prepare_document(document)
    rendered_document = _render_lua(prepared_document, 0)

    return (
        "-- Generated from data/retail-patch-notes.json. Do not edit.\n"
        "local _, addon = ...\n\n"
        f"addon.PatchNotesData = {rendered_document}\n"
    )


def generate_lua_file(data_path: Path, output_path: Path) -> None:
    document = json.loads(data_path.read_text(encoding="utf-8"))
    rendered_data = render_lua_data(document)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered_data, encoding="utf-8", newline="\n")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate WoW Lua patch-note data from canonical JSON.",
    )
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)

    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    try:
        generate_lua_file(arguments.data, arguments.output)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Generation failed: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
