from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable, NamedTuple
import os
import sys


SCHEMA_VERSION = 5
ENGLISH_LOCALE = "en"
FALLBACK_LOCALES = {
    "deDE",
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


class FallbackApplicationResult(NamedTuple):
    fallback_locales: tuple[str, ...]
    removed_localizations: int


def _require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")

    return value


def _require_changes(document: dict[str, object]) -> list[object]:
    changes = document.get("changes")
    if not isinstance(changes, list):
        raise ValueError("changes must be a list")

    return changes


def _load_document(path: Path, label: str) -> dict[str, object]:
    document = _require_dict(
        json.loads(path.read_text(encoding="utf-8")),
        label,
    )
    if document.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"{label} schemaVersion must be {SCHEMA_VERSION}")

    _require_changes(document)

    return document


def _english_snapshot(document: dict[str, object]) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for raw_change in _require_changes(document):
        change = _require_dict(raw_change, "each change")
        identifier = change.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("each change must have a non-empty id")

        localizations = _require_dict(
            change.get("localizations"),
            "localizations",
        )
        english = _require_dict(
            localizations.get(ENGLISH_LOCALE),
            "English localization",
        )
        snapshot[identifier] = {
            "channel": change.get("channel"),
            "category": change.get("category"),
            "date": change.get("date"),
            "patch": change.get("patch"),
            "en": english,
        }

    return snapshot


def _fallback_reasons(batch: dict[str, object]) -> dict[str, str]:
    completion = _require_dict(
        batch.get("localeCompletion"),
        "localeCompletion",
    )
    raw_fallbacks = _require_dict(
        completion.get("fallbacks"),
        "localeCompletion.fallbacks",
    )
    fallbacks: dict[str, str] = {}
    for locale, reason in raw_fallbacks.items():
        if locale not in FALLBACK_LOCALES:
            raise ValueError(f"unsupported fallback locale: {locale}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"fallback reason is required for {locale}")

        fallbacks[locale] = reason.strip()

    if not fallbacks:
        raise ValueError("at least one fallback locale is required")

    return fallbacks


def _strip_fallback_localizations(
    document: dict[str, object],
    fallback_locales: set[str],
) -> tuple[dict[str, object], int]:
    published = json.loads(json.dumps(document))
    removed = 0
    for raw_change in _require_changes(published):
        change = _require_dict(raw_change, "each change")
        localizations = _require_dict(
            change.get("localizations"),
            "localizations",
        )
        for locale in fallback_locales:
            if locale in localizations:
                del localizations[locale]
                removed += 1

    return published, removed


def _load_lua_renderer() -> Callable[[object], str]:
    project_root = Path(__file__).resolve().parents[3]
    generator_path = (
        project_root
        / "skills"
        / "fetch-retail-patch-notes"
        / "scripts"
        / "generate_lua_data.py"
    )
    spec = importlib.util.spec_from_file_location(
        "fallback_lua_generator",
        generator_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load Lua data generator")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.render_lua_data


def _write_temporary(path: Path, content: str) -> Path:
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


def apply_translation_fallbacks(
    *,
    data_path: Path,
    batch_path: Path,
    lua_path: Path,
) -> FallbackApplicationResult:
    canonical = _load_document(data_path, "canonical data")
    batch = _load_document(batch_path, "translation batch")
    if canonical.get("updatedAt") != batch.get("updatedAt"):
        raise ValueError("translation batch does not match canonical snapshot")
    if _english_snapshot(canonical) != _english_snapshot(batch):
        raise ValueError("translation batch English snapshot is stale")

    fallbacks = _fallback_reasons(batch)
    published, removed = _strip_fallback_localizations(
        canonical,
        set(fallbacks),
    )
    if removed == 0:
        raise ValueError("fallback locales were already absent")

    json_content = f"{json.dumps(published, ensure_ascii=False, indent=2)}\n"
    lua_content = _load_lua_renderer()(published)
    temporary_data = _write_temporary(data_path, json_content)
    temporary_lua = _write_temporary(lua_path, lua_content)

    try:
        os.replace(temporary_data, data_path)
        os.replace(temporary_lua, lua_path)
    finally:
        if temporary_data.exists():
            temporary_data.unlink()
        if temporary_lua.exists():
            temporary_lua.unlink()

    return FallbackApplicationResult(
        fallback_locales=tuple(sorted(fallbacks)),
        removed_localizations=removed,
    )


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply audited locale fallbacks to canonical patch notes.",
    )
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--lua-output", required=True, type=Path)

    return parser.parse_args()


def main() -> int:
    arguments = _parse_arguments()
    try:
        result = apply_translation_fallbacks(
            data_path=arguments.data,
            batch_path=arguments.batch,
            lua_path=arguments.lua_output,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Fallback application failed: {error}", file=sys.stderr)
        return 1

    print(
        "Applied English fallbacks for "
        f"{', '.join(result.fallback_locales)}; "
        f"removed {result.removed_localizations} localizations."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
