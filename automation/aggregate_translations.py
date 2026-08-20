from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from automation.coordinator import (
    REQUIRED_TRANSLATION_LOCALES,
    SUPPORTED_TRANSLATION_LOCALES,
)


def _require_dict(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def aggregate_locale_artifacts(
    english_document: dict[str, object],
    locale_documents: tuple[dict[str, object], ...],
) -> dict[str, object]:
    """Return one batch when required and supplied optional locales passed."""
    documents_by_locale: dict[str, dict[str, object]] = {}
    for document in locale_documents:
        locale = document.get("locale")
        if not isinstance(locale, str):
            raise ValueError("locale artifact has no locale")
        if locale in documents_by_locale:
            raise ValueError(f"duplicate locale artifact: {locale}")
        documents_by_locale[locale] = document

    required_locales = set(REQUIRED_TRANSLATION_LOCALES)
    actual_locales = set(documents_by_locale)
    missing_locales = required_locales - actual_locales
    unexpected_locales = actual_locales - SUPPORTED_TRANSLATION_LOCALES
    if missing_locales:
        raise ValueError(
            "missing locale artifacts: " + ", ".join(sorted(missing_locales))
        )
    if unexpected_locales:
        raise ValueError(
            "unexpected locale artifacts: "
            + ", ".join(sorted(unexpected_locales))
        )

    combined = deepcopy(english_document)
    combined["retrievedAt"] = combined.pop("updatedAt")
    combined_changes = _require_list(combined.get("changes"), "English changes")
    for raw_change in combined_changes:
        combined_change = _require_dict(raw_change, "English change")
        combined_change["replacesSourceUrl"] = ""
    semantic_approvals: list[object] = []

    for locale in sorted(actual_locales):
        artifact = documents_by_locale[locale]
        if artifact.get("status") != "PASS":
            reason = str(artifact.get("reason", "locale translation failed"))
            raise ValueError(f"{locale}: {reason}")
        batch = _require_dict(artifact.get("batch"), f"{locale} batch")
        locale_changes = _require_list(
            batch.get("changes"),
            f"{locale} changes",
        )
        if len(locale_changes) != len(combined_changes):
            raise ValueError(f"{locale} change count does not match English")

        for index, raw_locale_change in enumerate(locale_changes):
            locale_change = _require_dict(
                raw_locale_change,
                f"{locale} change {index}",
            )
            combined_change = _require_dict(
                combined_changes[index],
                f"English change {index}",
            )
            locale_localizations = _require_dict(
                locale_change.get("localizations"),
                f"{locale} localizations",
            )
            combined_localizations = _require_dict(
                combined_change.get("localizations"),
                "English localizations",
            )
            if locale_localizations.get("en") != combined_localizations.get("en"):
                raise ValueError(f"{locale} English baseline does not match")
            if locale not in locale_localizations:
                raise ValueError(f"{locale} localization is missing")
            combined_localizations[locale] = deepcopy(
                locale_localizations[locale]
            )

        semantic_approvals.extend(
            _require_list(
                batch.get("semanticApprovals", []),
                f"{locale} semantic approvals",
            )
        )
    if semantic_approvals:
        combined["semanticApprovals"] = semantic_approvals

    return combined


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_aggregation(
    *,
    acquisition_directory: Path,
    translations_directory: Path,
    result_path: Path,
    dry_run: bool,
) -> int:
    from automation.coordinator import coordinate_release
    from automation.models import RefreshOutcome, RefreshStatus
    from automation.reporting import summarize_terminology_warnings
    from automation.runner import (
        PROJECT_ROOT,
        _copy_release_files,
        _refresher,
        _release_files,
        _validator,
    )

    english_document: dict[str, object] = {}
    acquisition_result: dict[str, object] = {}
    try:
        english_path = acquisition_directory / "english-document.json"
        terminology_path = acquisition_directory / "runtime-terminology.json"
        acquisition_result_path = (
            acquisition_directory / "acquisition-result.json"
        )
        english_document = json.loads(
            english_path.read_text(encoding="utf-8")
        )
        acquisition_result = json.loads(
            acquisition_result_path.read_text(encoding="utf-8")
        )
        locale_documents = tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(
                translations_directory.glob("*/locale-result.json")
            )
        )
        combined = aggregate_locale_artifacts(
            english_document,
            locale_documents,
        )
        release_files = _release_files(PROJECT_ROOT)
        release_date = date.fromisoformat(
            str(english_document["updatedAt"]).split("T", 1)[0]
        )
        translate = lambda _document: combined
        validate = lambda batch: _validator(batch, terminology_path)
        if dry_run:
            with TemporaryDirectory() as temporary_directory:
                temporary_files = _copy_release_files(
                    release_files,
                    Path(temporary_directory),
                )
                outcome = coordinate_release(
                    files=temporary_files,
                    english_document=english_document,
                    current_patch=str(acquisition_result["current_patch"]),
                    release_date=release_date,
                    translate=translate,
                    validate=validate,
                    refresh=_refresher,
                )
        else:
            outcome = coordinate_release(
                files=release_files,
                english_document=english_document,
                current_patch=str(acquisition_result["current_patch"]),
                release_date=release_date,
                translate=translate,
                validate=validate,
                refresh=_refresher,
            )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        outcome = RefreshOutcome(
            status=RefreshStatus.BLOCKED,
            reason=str(error),
        )

    audit = asdict(outcome)
    warning_summary = summarize_terminology_warnings(
        outcome.terminology_warnings
    )
    audit["status"] = outcome.status.value
    audit["dryRun"] = dry_run
    audit["currentPatch"] = acquisition_result.get("current_patch", "")
    audit["asOfDate"] = str(english_document.get("updatedAt", "")).split(
        "T",
        1,
    )[0]
    audit["terminologyWarningCount"] = warning_summary.total
    audit["terminologyWarningsByLocale"] = warning_summary.by_locale
    _write_json(result_path, audit)

    return 0 if outcome.status != RefreshStatus.BLOCKED else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate validated locale artifacts into one release.",
    )
    parser.add_argument("--acquisition", required=True, type=Path)
    parser.add_argument("--translations", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    return run_aggregation(
        acquisition_directory=arguments.acquisition,
        translations_directory=arguments.translations,
        result_path=arguments.result,
        dry_run=arguments.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
