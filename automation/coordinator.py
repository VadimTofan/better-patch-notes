from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

from automation.models import (
    ExtractedChange,
    RefreshOutcome,
    RefreshStatus,
)
from automation.release_files import (
    ReleaseFiles,
    ReleaseSummary,
    has_meaningful_change,
    restore_snapshot,
    snapshot_files,
    update_release_files,
)
from automation.reporting import summarize_terminology_warnings


SUPPORTED_TRANSLATION_LOCALES = {
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


class TranslationReport(Protocol):
    validated_locales: tuple[str, ...]
    fallback_locales: tuple[str, ...]
    fallback_reasons: dict[str, str]
    uncertain_terms: tuple[str, ...]


class RefreshResult(Protocol):
    added: int
    skipped: int
    promoted: int
    localized: int
    ambiguous: int
    removed: int


Translator = Callable[[dict[str, object]], dict[str, object]]
Validator = Callable[[dict[str, object]], TranslationReport]
Refresher = Callable[[Path, Path, Path, str], RefreshResult]


def build_english_document(
    changes: tuple[ExtractedChange, ...],
    retrieved_at: str,
) -> dict[str, object]:
    return {
        "schemaVersion": 5,
        "updatedAt": retrieved_at,
        "changes": [
            {
                "channel": change.channel,
                "category": change.category,
                "date": change.effective_date.isoformat(),
                "patch": change.patch,
                "localizations": {
                    "en": {
                        "name": change.name,
                        "specialization": change.specialization,
                        "source": "Blizzard",
                        "sourceUrl": change.source_url,
                        "translationType": "official",
                        "translatedFrom": "",
                        "change": list(change.change),
                        "terminologySourceUrls": [],
                    }
                },
            }
            for change in changes
        ],
    }


def _prepare_locale_outcomes(
    batch: dict[str, object],
    report: TranslationReport,
) -> None:
    validated = set(report.validated_locales)
    fallback = set(report.fallback_locales)
    classified = validated | fallback
    missing_report_locales = SUPPORTED_TRANSLATION_LOCALES - classified
    unexpected_locales = classified - SUPPORTED_TRANSLATION_LOCALES
    if missing_report_locales or unexpected_locales or validated & fallback:
        raise ValueError(
            "translation locale outcomes are incomplete or conflicting"
        )

    fallback_reasons = report.fallback_reasons
    if set(fallback_reasons) != fallback:
        raise ValueError("every English fallback requires one reason")
    if any(not reason.strip() for reason in fallback_reasons.values()):
        raise ValueError("English fallback reasons must not be empty")

    changes = batch.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("translation batch must contain changes")
    required_locales = validated | {"en"}
    for index, raw_change in enumerate(changes):
        if not isinstance(raw_change, dict):
            raise ValueError(f"translation change {index} must be an object")
        localizations = raw_change.get("localizations")
        if not isinstance(localizations, dict):
            raise ValueError(
                f"translation change {index} has no localizations",
            )
        for locale in fallback:
            localizations.pop(locale, None)

        missing = required_locales - set(localizations)
        if missing:
            raise ValueError(
                f"translation change {index} is missing: "
                + ", ".join(sorted(missing))
            )
        for locale in validated:
            localization = localizations[locale]
            if not isinstance(localization, dict):
                raise ValueError(f"{locale} localization must be an object")


def _ptr_patch(document: dict[str, object]) -> str:
    patches = {
        str(change["patch"])
        for change in document["changes"]
        if change["channel"] == "ptr"
    }
    if not patches:
        return "None"

    return ", ".join(sorted(patches))


def coordinate_release(
    *,
    files: ReleaseFiles,
    english_document: dict[str, object],
    current_patch: str,
    release_date: date,
    translate: Translator,
    validate: Validator,
    refresh: Refresher,
) -> RefreshOutcome:
    snapshot = snapshot_files(files)
    try:
        before = json.loads(files.data.read_text(encoding="utf-8"))
        has_incoming_changes = bool(english_document.get("changes"))
        terminology_warnings: tuple[str, ...] = ()
        validated_locales: tuple[str, ...] = ()
        fallback_reasons: dict[str, str] = {}
        if has_incoming_changes:
            batch = translate(deepcopy(english_document))
            report = validate(batch)
            _prepare_locale_outcomes(batch, report)
            terminology_warnings = report.uncertain_terms
            validated_locales = report.validated_locales
            fallback_reasons = report.fallback_reasons
        else:
            batch = {
                "retrievedAt": english_document["updatedAt"],
                "changes": [],
            }

        with TemporaryDirectory() as temporary_directory:
            batch_path = Path(temporary_directory) / "translation-batch.json"
            batch_path.write_text(
                json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            refresh_result = refresh(
                batch_path,
                files.data,
                files.lua,
                current_patch,
            )

        if refresh_result.ambiguous:
            raise ValueError(
                f"refresh produced {refresh_result.ambiguous} ambiguous records",
            )

        after = json.loads(files.data.read_text(encoding="utf-8"))
        if not has_meaningful_change(before, after):
            restore_snapshot(snapshot)
            return RefreshOutcome(
                status=RefreshStatus.NO_CHANGE,
                terminology_warnings=terminology_warnings,
            )

        warning_summary = summarize_terminology_warnings(
            terminology_warnings
        )
        validated_text = ", ".join(validated_locales) or "None"
        fallback_text = (
            ", ".join(
                f"{locale} ({fallback_reasons[locale]})"
                for locale in sorted(fallback_reasons)
            )
            or "None"
        )
        summary = ReleaseSummary(
            live_patch=current_patch,
            ptr_patch=_ptr_patch(english_document),
            added=refresh_result.added,
            updated=refresh_result.promoted + refresh_result.localized,
            removed=refresh_result.removed,
            locale_text=(
                f"Validated {validated_text}; English fallbacks: "
                f"{fallback_text}; "
                + warning_summary.changelog_text
                if has_incoming_changes
                else "No new localized records; retained records unchanged"
            ),
        )
        version = update_release_files(files, release_date, summary)

        return RefreshOutcome(
            status=RefreshStatus.RELEASE_READY,
            added=refresh_result.added,
            updated=refresh_result.promoted + refresh_result.localized,
            removed=refresh_result.removed,
            version=version,
            terminology_warnings=terminology_warnings,
        )
    except Exception as error:
        restore_snapshot(snapshot)
        return RefreshOutcome(
            status=RefreshStatus.BLOCKED,
            reason=str(error),
        )


def main() -> int:
    from automation.runner import main as runner_main

    return runner_main()


if __name__ == "__main__":
    raise SystemExit(main())
