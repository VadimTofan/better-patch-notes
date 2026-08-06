from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import date, datetime
from difflib import SequenceMatcher
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse


SCHEMA_VERSION = 5
VALID_CATEGORIES = frozenset({"Class", "Dungeon", "Raid"})
VALID_CHANNELS = frozenset({"live", "ptr"})
VALID_LOCALES = frozenset(
    {
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
)
INPUT_FIELDS = (
    "channel",
    "category",
    "date",
    "patch",
    "localizations",
    "replacesSourceUrl",
)
STORED_FIELDS = (
    "id",
    "channel",
    "category",
    "date",
    "patch",
    "localizations",
    "retrievedAt",
)
LOCALIZATION_FIELDS = (
    "name",
    "specialization",
    "change",
    "source",
    "sourceUrl",
    "translationType",
    "translatedFrom",
    "terminologySourceUrls",
)
LEGACY_STORED_FIELDS = (
    "id",
    "category",
    "name",
    "specialization",
    "change",
    "date",
    "patch",
    "source",
    "sourceUrl",
    "retrievedAt",
)
CHANGE_ID_PATTERN = re.compile(r"^change-[0-9a-f]{16}$")


@dataclass(frozen=True, slots=True)
class UpdateResult:
    added: int = 0
    skipped: int = 0
    promoted: int = 0
    localized: int = 0
    ambiguous: int = 0


def _require_object_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")

    return value


def _require_string(values: dict[str, object], field: str) -> str:
    value = values.get(field)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")

    return value.strip()


def _validate_timestamp(value: str, field: str) -> None:
    try:
        datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO 8601 timestamp") from error


def _validate_url(value: str, field: str) -> None:
    parsed_url = urlparse(value)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError(f"{field} must be an HTTP or HTTPS URL")


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _source_rank(source: str) -> int:
    normalized_source = _normalize_text(source)
    if "blizzard" in normalized_source:
        return 3
    if normalized_source in {"wowhead", "mmo-champion", "mmo champion"}:
        return 2

    return 1


def _require_change_list(value: object, locale: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"localization {locale} change must be a list")
    if not value:
        raise ValueError(f"localization {locale} change must not be empty")

    normalized_changes: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(
                f"localization {locale} change items must be non-empty strings"
            )
        normalized_changes.append(item.strip())

    return normalized_changes


def _require_url_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")

    normalized_urls: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} items must be non-empty strings")
        url = item.strip()
        _validate_url(url, field)
        normalized_urls.append(url)

    return normalized_urls


def _validate_localization(
    value: object,
    locale: str,
) -> dict[str, object]:
    localization = dict(
        _require_object_dict(value, f"localization {locale}")
    )
    localization.setdefault("translationType", "official")
    localization.setdefault("translatedFrom", "")
    localization.setdefault("terminologySourceUrls", [])
    missing_fields = [
        field for field in LOCALIZATION_FIELDS if field not in localization
    ]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(
            f"localization {locale} is missing required fields: {missing}"
        )

    normalized: dict[str, object] = {
        field: _require_string(localization, field)
        for field in LOCALIZATION_FIELDS
        if field not in {"change", "terminologySourceUrls"}
    }
    normalized["change"] = _require_change_list(
        localization["change"],
        locale,
    )
    normalized["terminologySourceUrls"] = _require_url_list(
        localization["terminologySourceUrls"],
        f"localization {locale} terminologySourceUrls",
    )
    if not normalized["name"]:
        raise ValueError(f"localization {locale} name must not be empty")
    if not normalized["source"]:
        raise ValueError(f"localization {locale} source must not be empty")
    if locale != "en" and _normalize_text(normalized["source"]) != "blizzard":
        raise ValueError(
            f"localization {locale} must use an official Blizzard translation"
        )
    _validate_url(str(normalized["sourceUrl"]), f"{locale} sourceUrl")

    translation_type = normalized["translationType"]
    translated_from = normalized["translatedFrom"]
    terminology_urls = normalized["terminologySourceUrls"]
    if translation_type not in {"official", "agent"}:
        raise ValueError(
            f"localization {locale} translationType must be official or agent"
        )
    if translation_type == "official":
        if translated_from:
            raise ValueError(
                f"official localization {locale} translatedFrom must be empty"
            )
        if terminology_urls:
            raise ValueError(
                f"official localization {locale} terminologySourceUrls "
                "must be empty"
            )
    else:
        if locale == "en":
            raise ValueError("en localization must be official")
        if translated_from != "en":
            raise ValueError(
                f"agent localization {locale} translatedFrom must be en"
            )
        if not terminology_urls:
            raise ValueError(
                f"agent localization {locale} terminologySourceUrls "
                "must not be empty"
            )

    return normalized


def _validate_localizations(
    value: object,
) -> dict[str, dict[str, object]]:
    localizations = _require_object_dict(value, "localizations")
    if "en" not in localizations:
        raise ValueError("localizations must include en as the English fallback")

    unknown_locales = sorted(set(localizations) - VALID_LOCALES)
    if unknown_locales:
        raise ValueError(
            f"unsupported locale: {', '.join(unknown_locales)}"
        )

    validated = {
        locale: _validate_localization(localization, locale)
        for locale, localization in localizations.items()
    }
    english_source_url = validated["en"]["sourceUrl"]
    for locale, localization in validated.items():
        if (
            localization["translationType"] == "agent"
            and localization["sourceUrl"] != english_source_url
        ):
            raise ValueError(
                f"agent localization {locale} must retain the en sourceUrl"
            )

    return validated


def _validate_common_fields(change: dict[str, object]) -> None:
    if change["channel"] not in VALID_CHANNELS:
        raise ValueError("channel must be live or ptr")
    if change["category"] not in VALID_CATEGORIES:
        raise ValueError("category must be Class, Dungeon, or Raid")

    try:
        date.fromisoformat(str(change["date"]))
    except ValueError as error:
        raise ValueError("date must use YYYY-MM-DD") from error


def _validate_input_change(value: object) -> dict[str, object]:
    change = _require_object_dict(value, "each change")
    missing_fields = [field for field in INPUT_FIELDS if field not in change]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"change is missing required fields: {missing}")

    normalized: dict[str, object] = {
        "channel": _require_string(change, "channel"),
        "category": _require_string(change, "category"),
        "date": _require_string(change, "date"),
        "patch": _require_string(change, "patch"),
        "localizations": _validate_localizations(change["localizations"]),
        "replacesSourceUrl": _require_string(
            change,
            "replacesSourceUrl",
        ),
    }
    _validate_common_fields(normalized)
    replacement_url = str(normalized["replacesSourceUrl"])
    if replacement_url:
        _validate_url(replacement_url, "replacesSourceUrl")

    return normalized


def _validate_stored_change(value: object) -> dict[str, object]:
    change = _require_object_dict(value, "each stored change")
    missing_fields = [field for field in STORED_FIELDS if field not in change]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"stored change is missing required fields: {missing}")

    normalized: dict[str, object] = {
        "id": _require_string(change, "id"),
        "channel": _require_string(change, "channel"),
        "category": _require_string(change, "category"),
        "date": _require_string(change, "date"),
        "patch": _require_string(change, "patch"),
        "localizations": _validate_localizations(change["localizations"]),
        "retrievedAt": _require_string(change, "retrievedAt"),
    }
    _validate_common_fields(normalized)
    _validate_timestamp(str(normalized["retrievedAt"]), "retrievedAt")
    if not CHANGE_ID_PATTERN.fullmatch(str(normalized["id"])):
        raise ValueError("stored change id has an invalid format")

    return normalized


def _migrate_schema_one_change(value: object) -> dict[str, object]:
    change = _require_object_dict(value, "each legacy stored change")
    missing_fields = [
        field for field in LEGACY_STORED_FIELDS if field not in change
    ]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(
            f"legacy stored change is missing required fields: {missing}"
        )

    identifier = _require_string(change, "id")
    retrieved_at = _require_string(change, "retrievedAt")
    if not CHANGE_ID_PATTERN.fullmatch(identifier):
        raise ValueError("legacy stored change id has an invalid format")
    _validate_timestamp(retrieved_at, "retrievedAt")

    migrated: dict[str, object] = {
        "id": identifier,
        "channel": "live",
        "category": _require_string(change, "category"),
        "date": _require_string(change, "date"),
        "patch": _require_string(change, "patch"),
        "localizations": {
            "en": {
                "name": _require_string(change, "name"),
                "specialization": _require_string(
                    change,
                    "specialization",
                ),
                "change": [_require_string(change, "change")],
                "source": _require_string(change, "source"),
                "sourceUrl": _require_string(change, "sourceUrl"),
                "translationType": "official",
                "translatedFrom": "",
                "terminologySourceUrls": [],
            }
        },
        "retrievedAt": retrieved_at,
    }

    return _migrate_schema_three_change(migrated)


def _migrate_schema_three_change(value: object) -> dict[str, object]:
    change = _require_object_dict(value, "each schema-three stored change")
    migrated = dict(change)
    localizations = _require_object_dict(
        change.get("localizations"),
        "localizations",
    )
    migrated_localizations: dict[str, object] = {}
    for locale, raw_localization in localizations.items():
        localization = dict(
            _require_object_dict(
                raw_localization,
                f"localization {locale}",
            )
        )
        localization.setdefault("translationType", "official")
        localization.setdefault("translatedFrom", "")
        localization.setdefault("terminologySourceUrls", [])
        migrated_localizations[locale] = localization

    migrated["localizations"] = migrated_localizations

    return _migrate_schema_four_change(migrated)


def _migrate_schema_four_change(value: object) -> dict[str, object]:
    change = _require_object_dict(value, "each schema-four stored change")
    migrated = dict(change)
    localizations = _require_object_dict(
        change.get("localizations"),
        "localizations",
    )
    migrated_localizations = {
        locale: dict(
            _require_object_dict(
                raw_localization,
                f"localization {locale}",
            )
        )
        for locale, raw_localization in localizations.items()
        if locale not in {"enGB", "enUS"}
    }

    english_locale = next(
        (
            locale
            for locale in ("enUS", "en", "enGB")
            if locale in localizations
        ),
        None,
    )
    if english_locale is not None:
        migrated_localizations["en"] = dict(
            _require_object_dict(
                localizations[english_locale],
                f"localization {english_locale}",
            )
        )

    for locale, localization in migrated_localizations.items():
        if locale != "en" and localization.get("translatedFrom") in {
            "enGB",
            "enUS",
        }:
            localization["translatedFrom"] = "en"

    migrated["localizations"] = migrated_localizations

    return _validate_stored_change(migrated)


def _migrate_schema_two_change(value: object) -> dict[str, object]:
    change = _require_object_dict(value, "each schema-two stored change")
    migrated = dict(change)
    localizations = _require_object_dict(
        change.get("localizations"),
        "localizations",
    )
    migrated_localizations: dict[str, object] = {}
    for locale, raw_localization in localizations.items():
        localization = _require_object_dict(
            raw_localization,
            f"localization {locale}",
        )
        migrated_localization = dict(localization)
        legacy_change = _require_string(localization, "change")
        migrated_localization["change"] = [legacy_change]
        migrated_localizations[locale] = migrated_localization

    migrated["localizations"] = migrated_localizations

    return _migrate_schema_three_change(migrated)


def _validate_batch(value: object) -> tuple[str, list[dict[str, object]]]:
    batch = _require_object_dict(value, "batch")
    retrieved_at = _require_string(batch, "retrievedAt")
    _validate_timestamp(retrieved_at, "retrievedAt")
    changes = batch.get("changes")
    if not isinstance(changes, list):
        raise ValueError("changes must be a list")

    return retrieved_at, [
        _validate_input_change(change) for change in changes
    ]


def _load_data(data_path: Path) -> tuple[list[dict[str, object]], bool]:
    if not data_path.exists():
        return [], False

    document = _require_object_dict(
        json.loads(data_path.read_text(encoding="utf-8")),
        "canonical data",
    )
    schema_version = document.get("schemaVersion")
    if schema_version not in {1, 2, 3, 4, SCHEMA_VERSION}:
        raise ValueError(f"unsupported schemaVersion: {schema_version}")

    updated_at = _require_string(document, "updatedAt")
    _validate_timestamp(updated_at, "updatedAt")
    changes = document.get("changes")
    if not isinstance(changes, list):
        raise ValueError("canonical changes must be a list")

    migrated = schema_version != SCHEMA_VERSION
    validators = {
        1: _migrate_schema_one_change,
        2: _migrate_schema_two_change,
        3: _migrate_schema_three_change,
        4: _migrate_schema_four_change,
        SCHEMA_VERSION: _validate_stored_change,
    }
    validator = validators[schema_version]
    validated_changes = [validator(change) for change in changes]
    identifiers = [str(change["id"]) for change in validated_changes]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("canonical data contains duplicate change ids")

    return validated_changes, migrated


def _english(change: dict[str, object]) -> dict[str, object]:
    localizations = change["localizations"]
    assert isinstance(localizations, dict)
    english = localizations["en"]
    assert isinstance(english, dict)

    return english


def _grouping_key(change: dict[str, object]) -> tuple[object, ...]:
    localization_contexts: list[tuple[str, ...]] = []
    localizations = dict(change["localizations"])
    for locale, raw_localization in sorted(localizations.items()):
        localization = dict(raw_localization)
        localization_contexts.append(
            tuple(
                _normalize_text(str(value))
                for value in (
                    locale,
                    localization["name"],
                    localization["specialization"],
                    localization["source"],
                    localization["sourceUrl"],
                    localization["translationType"],
                    localization["translatedFrom"],
                    "\n".join(localization["terminologySourceUrls"]),
                )
            )
        )

    return (
        _normalize_text(str(change["channel"])),
        _normalize_text(str(change["category"])),
        _normalize_text(str(change["date"])),
        _normalize_text(str(change["patch"])),
        _normalize_text(str(change.get("replacesSourceUrl", ""))),
        tuple(localization_contexts),
    )


def _copy_change(change: dict[str, object]) -> dict[str, object]:
    copied = dict(change)
    copied["localizations"] = {
        locale: {
            **dict(raw_localization),
            "change": list(dict(raw_localization)["change"]),
            "terminologySourceUrls": list(
                dict(raw_localization)["terminologySourceUrls"]
            ),
        }
        for locale, raw_localization in dict(
            change["localizations"]
        ).items()
    }

    return copied


def _append_change_items(
    existing: dict[str, object],
    additional: dict[str, object],
) -> None:
    existing_localizations = dict(existing["localizations"])
    additional_localizations = dict(additional["localizations"])
    for locale, raw_existing in existing_localizations.items():
        existing_localization = dict(raw_existing)
        additional_localization = dict(additional_localizations[locale])
        existing_items = list(existing_localization["change"])
        for item in additional_localization["change"]:
            if item not in existing_items:
                existing_items.append(item)
        existing_localization["change"] = existing_items
        existing_localizations[locale] = existing_localization

    existing["localizations"] = existing_localizations
    if "retrievedAt" in existing and "retrievedAt" in additional:
        existing["retrievedAt"] = max(
            str(existing["retrievedAt"]),
            str(additional["retrievedAt"]),
        )


def _consolidate_changes(
    changes: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    consolidated: list[dict[str, object]] = []
    indexes_by_context: dict[tuple[object, ...], int] = {}
    grouped_count = 0

    for change in changes:
        key = _grouping_key(change)
        existing_index = indexes_by_context.get(key)
        if existing_index is None:
            indexes_by_context[key] = len(consolidated)
            consolidated.append(_copy_change(change))
            continue

        _append_change_items(consolidated[existing_index], change)
        grouped_count += 1

    return consolidated, grouped_count


def _identity(change: dict[str, object]) -> tuple[str, ...]:
    english = _english(change)
    change_items = english["change"]
    assert isinstance(change_items, list)

    return tuple(
        _normalize_text(str(value))
        for value in (
            change["channel"],
            change["category"],
            english["name"],
            english["specialization"],
            "\n".join(str(item) for item in change_items),
            change["date"],
        )
    )


def _context(change: dict[str, object]) -> tuple[str, ...]:
    identity = _identity(change)

    return identity[0:4] + (identity[5],)


def _generate_id(change: dict[str, object]) -> str:
    identity_text = "|".join(_identity(change)).encode("utf-8")
    digest = sha256(identity_text).hexdigest()[:16]

    return f"change-{digest}"


def _stored_change(
    incoming: dict[str, object],
    retrieved_at: str,
    identifier: str | None = None,
) -> dict[str, object]:
    return {
        "id": identifier or _generate_id(incoming),
        "channel": incoming["channel"],
        "category": incoming["category"],
        "date": incoming["date"],
        "patch": incoming["patch"],
        "localizations": {
            locale: dict(localization)
            for locale, localization in dict(
                incoming["localizations"]
            ).items()
        },
        "retrievedAt": retrieved_at,
    }


def _all_source_urls(change: dict[str, object]) -> set[str]:
    return {
        localization["sourceUrl"]
        for localization in dict(change["localizations"]).values()
    }


def _has_ambiguous_match(
    existing_changes: list[dict[str, object]],
    incoming: dict[str, object],
) -> bool:
    incoming_english = _english(incoming)
    for existing in existing_changes:
        if incoming_english["sourceUrl"] in _all_source_urls(existing):
            continue
        if _context(existing) != _context(incoming):
            continue

        for existing_item in _english(existing)["change"]:
            for incoming_item in incoming_english["change"]:
                similarity = SequenceMatcher(
                    None,
                    _normalize_text(str(existing_item)),
                    _normalize_text(str(incoming_item)),
                ).ratio()
                if similarity >= 0.75:
                    return True

    return False


def _sort_key(change: dict[str, object]) -> tuple[object, ...]:
    english = _english(change)

    return (
        -date.fromisoformat(str(change["date"])).toordinal(),
        str(change["channel"]).casefold(),
        str(change["category"]).casefold(),
        str(english["name"]).casefold(),
        str(english["specialization"]).casefold(),
        tuple(
            str(item).casefold()
            for item in english["change"]
        ),
    )


def _save_atomically(
    data_path: Path,
    changes: list[dict[str, object]],
    updated_at: str,
) -> None:
    data_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schemaVersion": SCHEMA_VERSION,
        "updatedAt": updated_at,
        "changes": sorted(changes, key=_sort_key),
    }
    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=data_path.parent,
            suffix=".json.tmp",
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(
                document,
                temporary_file,
                ensure_ascii=False,
                indent=2,
            )
            temporary_file.write("\n")

        os.replace(temporary_path, data_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _merge_localizations(
    existing: dict[str, object],
    incoming: dict[str, object],
) -> tuple[int, int]:
    existing_localizations = dict(existing["localizations"])
    incoming_localizations = dict(incoming["localizations"])
    localized = 0
    promoted = 0

    for locale, incoming_localization in incoming_localizations.items():
        existing_localization = existing_localizations.get(locale)
        if existing_localization is None:
            existing_localizations[locale] = dict(incoming_localization)
            localized += 1
            continue

        incoming_source_rank = _source_rank(incoming_localization["source"])
        existing_source_rank = _source_rank(existing_localization["source"])
        incoming_translation_rank = (
            2 if incoming_localization["translationType"] == "official" else 1
        )
        existing_translation_rank = (
            2 if existing_localization["translationType"] == "official" else 1
        )
        if (
            incoming_source_rank > existing_source_rank
            or (
                incoming_source_rank == existing_source_rank
                and incoming_translation_rank > existing_translation_rank
            )
        ):
            existing_localizations[locale] = dict(incoming_localization)
            promoted += 1

    existing["localizations"] = existing_localizations

    return localized, promoted


def update_data(
    data_path: Path,
    incoming_changes: list[dict[str, object]],
    retrieved_at: str,
) -> UpdateResult:
    stored_changes, migrated = _load_data(data_path)
    stored_changes, consolidated_existing = _consolidate_changes(
        stored_changes
    )
    incoming_changes, _ = _consolidate_changes(incoming_changes)
    added = 0
    skipped = 0
    promoted = 0
    localized = 0
    ambiguous = 0

    for incoming in incoming_changes:
        incoming_identity = _identity(incoming)
        exact_index = next(
            (
                index
                for index, existing in enumerate(stored_changes)
                if _identity(existing) == incoming_identity
            ),
            None,
        )
        if exact_index is not None:
            existing = stored_changes[exact_index]
            added_locales, promoted_locales = _merge_localizations(
                existing,
                incoming,
            )
            localized += added_locales
            promoted += promoted_locales
            if added_locales or promoted_locales:
                existing["retrievedAt"] = retrieved_at
            else:
                skipped += 1
            continue

        replacement_url = str(incoming["replacesSourceUrl"])
        if replacement_url:
            replacement_index = next(
                (
                    index
                    for index, existing in enumerate(stored_changes)
                    if replacement_url in _all_source_urls(existing)
                ),
                None,
            )
            if replacement_index is None:
                raise ValueError(
                    "replacesSourceUrl does not match an existing change"
                )

            existing = stored_changes[replacement_index]
            if _context(existing) != _context(incoming):
                raise ValueError(
                    "replacement must keep channel, category, English name, "
                    "specialization, and date"
                )

            if _source_rank(_english(incoming)["source"]) > _source_rank(
                _english(existing)["source"]
            ):
                replacement = _stored_change(
                    incoming,
                    retrieved_at,
                    str(existing["id"]),
                )
                existing_localizations = dict(existing["localizations"])
                existing_localizations.update(
                    dict(replacement["localizations"])
                )
                replacement["localizations"] = existing_localizations
                stored_changes[replacement_index] = replacement
                promoted += 1
            else:
                skipped += 1
            continue

        if _has_ambiguous_match(stored_changes, incoming):
            ambiguous += 1

        stored_changes.append(_stored_change(incoming, retrieved_at))
        added += 1

    if (
        added
        or promoted
        or localized
        or migrated
        or consolidated_existing
        or not data_path.exists()
    ):
        _save_atomically(data_path, stored_changes, retrieved_at)

    return UpdateResult(
        added=added,
        skipped=skipped,
        promoted=promoted,
        localized=localized,
        ambiguous=ambiguous,
    )


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely update canonical Retail patch-note JSON.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)

    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()

    try:
        batch = json.loads(arguments.input.read_text(encoding="utf-8"))
        retrieved_at, incoming_changes = _validate_batch(batch)
        result = update_data(
            arguments.data,
            incoming_changes,
            retrieved_at,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Update failed: {error}", file=sys.stderr)
        return 1

    print(json.dumps(asdict(result), sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
