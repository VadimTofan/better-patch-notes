from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Protocol
from urllib.parse import urlsplit

from automation.coordinator import (
    SUPPORTED_TRANSLATION_LOCALES,
    build_english_document,
    coordinate_release,
)
from automation.discovery import (
    discover_forum_documents,
    discover_forum_topic_urls,
    discover_news_documents,
)
from automation.extraction import AmbiguousPatchNote, extract_changes
from automation.http_client import BlizzardHttpClient
from automation.models import (
    HttpResponse,
    RefreshOutcome,
    RefreshStatus,
    SourceDocument,
    SourceRegistry,
)
from automation.qualification import QualificationResult, qualify, resolve_retail_patch
from automation.release_files import ReleaseFiles
from automation.reporting import (
    redact_secrets,
    summarize_terminology_warnings,
)
from automation.source_registry import load_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORK_DIRECTORY = PROJECT_ROOT / ".bpn-work"
RESULT_PATH = WORK_DIRECTORY / "automation-result.json"
COLLECTION_PATH = WORK_DIRECTORY / "collection.json"
TRANSLATION_SCRIPT = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "scripts"
    / "generate_translations.py"
)
VALIDATION_SCRIPT = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "scripts"
    / "validate_translations.py"
)
REFRESH_SCRIPT = (
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "scripts"
    / "refresh_patch_notes.py"
)
TERMINOLOGY_PATH = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "references"
    / "terminology.json"
)
RUNTIME_TERMINOLOGY_PATH = WORK_DIRECTORY / "runtime-terminology.json"


class HttpClient(Protocol):
    def get(self, url: str) -> HttpResponse: ...


def _official_terminology_url(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "news.blizzard.com",
        "worldofwarcraft.blizzard.com",
    }:
        return None

    return url


def build_runtime_terminology(
    base: dict[str, object],
    canonical: dict[str, object],
) -> dict[str, object]:
    terminology = deepcopy(base)
    locales = terminology.get("locales")
    changes = canonical.get("changes")
    if not isinstance(locales, dict) or not isinstance(changes, list):
        raise ValueError("terminology or canonical data has an invalid shape")

    for raw_change in changes:
        if not isinstance(raw_change, dict):
            raise ValueError("canonical change must be an object")
        localizations = raw_change.get("localizations")
        if not isinstance(localizations, dict):
            raise ValueError("canonical change has no localizations")
        english = localizations.get("en")
        if not isinstance(english, dict):
            raise ValueError("canonical change has no English localization")

        for locale, locale_data in locales.items():
            localized = localizations.get(locale)
            if not isinstance(locale_data, dict) or not isinstance(localized, dict):
                continue
            terms = locale_data.get("terms")
            urls = localized.get("terminologySourceUrls")
            if not isinstance(terms, dict) or not isinstance(urls, list):
                continue
            source_url = next(
                (
                    official_url
                    for url in urls
                    if (official_url := _official_terminology_url(url))
                ),
                None,
            )
            if source_url is None:
                continue

            for field in ("name", "specialization"):
                english_term = english.get(field)
                localized_term = localized.get(field)
                if (
                    not isinstance(english_term, str)
                    or not english_term
                    or english_term == "All"
                    or not isinstance(localized_term, str)
                    or not localized_term
                ):
                    continue
                existing = terms.get(english_term)
                if isinstance(existing, dict):
                    if existing.get("localized") != localized_term:
                        raise ValueError(
                            f"conflicting terminology for {locale}: "
                            f"{english_term}",
                        )
                    continue
                terms[english_term] = {
                    "localized": localized_term,
                    "sourceUrl": source_url,
                }

    return terminology


def _hydrate(document: SourceDocument, response: HttpResponse) -> SourceDocument:
    return replace(
        document,
        url=response.final_url,
        body=response.body,
        mime_type=response.mime_type,
        content_hash=response.content_hash,
    )


def collect_official_documents(
    *,
    registry: SourceRegistry,
    client: HttpClient,
) -> tuple[str, tuple[SourceDocument, ...]]:
    version_responses: list[bytes] = []
    documents: list[SourceDocument] = []

    for source in registry.sources:
        if source.kind == "version":
            version_responses.append(client.get(source.url).body)
            continue

        response_url = (
            f"{source.url}.json"
            if source.kind == "forum_topic" and not source.url.endswith(".json")
            else source.url
        )
        response = client.get(response_url)
        if source.kind == "news_feed":
            discovered = discover_news_documents(response.body, source)
            documents.extend(
                _hydrate(document, client.get(document.url))
                for document in discovered
            )
        elif source.kind == "forum_category":
            for topic_url in discover_forum_topic_urls(response.body, source):
                topic_response = client.get(topic_url)
                documents.extend(
                    discover_forum_documents(
                        topic_response.body,
                        source,
                        registry.blue_authors,
                    )
                )
        elif source.kind == "forum_topic":
            documents.extend(
                discover_forum_documents(
                    response.body,
                    source,
                    registry.blue_authors,
                )
            )
        else:
            raise ValueError(f"unsupported source kind: {source.kind}")

    current_patch = resolve_retail_patch(tuple(version_responses))

    return current_patch, tuple(documents)


def _qualify_documents(
    documents: tuple[SourceDocument, ...],
    current_patch: str,
    as_of_date: date,
) -> QualificationResult:
    extracted_changes = []
    for document in documents:
        try:
            extracted_changes.extend(
                extract_changes(
                    document,
                    earliest_date=as_of_date - timedelta(days=13),
                    latest_date=as_of_date,
                )
            )
        except AmbiguousPatchNote as error:
            raise AmbiguousPatchNote(
                f"{document.url}: {error}",
            ) from error

    return qualify(tuple(extracted_changes), current_patch, as_of_date)


def collect_official_changes(
    *,
    registry: SourceRegistry,
    client: HttpClient,
    as_of_date: date,
) -> tuple[str, QualificationResult, tuple[SourceDocument, ...]]:
    current_patch, documents = collect_official_documents(
        registry=registry,
        client=client,
    )
    result = _qualify_documents(documents, current_patch, as_of_date)

    return current_patch, result, tuple(documents)


def _release_files(root: Path) -> ReleaseFiles:
    return ReleaseFiles(
        toc=root / "BetterPatchNotes.toc",
        addon=root / "Addon.lua",
        readme=root / "README.md",
        changelog=root / "changelog.txt",
        data=root / "data" / "retail-patch-notes.json",
        lua=root / "PatchNotesData.lua",
    )


def _run(command: list[str]) -> str:
    child_environment = os.environ.copy()
    child_environment["PYTHONUTF8"] = "1"
    child_environment["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=child_environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode:
        standard_error = (completed.stderr or "").strip()
        standard_output = (completed.stdout or "").strip()
        message = standard_error or standard_output
        raise RuntimeError(redact_secrets(message[-2000:]))

    return (completed.stdout or "").strip()


def _translator(
    document: dict[str, object],
    terminology_path: Path,
) -> dict[str, object]:
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        input_path = temporary_root / "english.json"
        output_path = temporary_root / "translated.json"
        input_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            _run(
                [
                    sys.executable,
                    str(TRANSLATION_SCRIPT),
                    "--input",
                    str(input_path),
                    "--output",
                    str(output_path),
                    "--terminology",
                    str(terminology_path),
                ]
            )
            batch = json.loads(output_path.read_text(encoding="utf-8"))
        except RuntimeError:
            batch = {
                "retrievedAt": document["updatedAt"],
                "fallbackReasons": {
                    locale: "automatic translation generation failed"
                    for locale in sorted(SUPPORTED_TRANSLATION_LOCALES)
                },
                "changes": deepcopy(document["changes"]),
            }
            for change in batch["changes"]:
                change["replacesSourceUrl"] = ""

        WORK_DIRECTORY.mkdir(parents=True, exist_ok=True)
        (WORK_DIRECTORY / "translation-batch.json").write_text(
            json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return batch


def _validator(
    batch: dict[str, object],
    terminology_path: Path,
) -> SimpleNamespace:
    with TemporaryDirectory() as temporary_directory:
        input_path = Path(temporary_directory) / "translated.json"
        input_path.write_text(
            json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output = _run(
            [
                sys.executable,
                str(VALIDATION_SCRIPT),
                "--input",
                str(input_path),
                "--terminology",
                str(terminology_path),
            ]
        )
        report = json.loads(output.splitlines()[-1])

        return SimpleNamespace(
            validated_locales=tuple(report["validated_locales"]),
            fallback_locales=tuple(report["fallback_locales"]),
            fallback_reasons=dict(report["fallback_reasons"]),
            uncertain_terms=tuple(report["uncertain_terms"]),
        )


def _refresher(
    batch_path: Path,
    data_path: Path,
    lua_path: Path,
    current_patch: str,
) -> SimpleNamespace:
    output = _run(
        [
            sys.executable,
            str(REFRESH_SCRIPT),
            "--input",
            str(batch_path),
            "--data",
            str(data_path),
            "--lua-output",
            str(lua_path),
            "--game-version",
            current_patch,
        ]
    )
    result = json.loads(output.splitlines()[-1])

    return SimpleNamespace(**result)


def _copy_release_files(source: ReleaseFiles, destination: Path) -> ReleaseFiles:
    destination_files = _release_files(destination)
    for source_path, destination_path in zip(
        source.paths(),
        destination_files.paths(),
        strict=True,
    ):
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(source_path.read_bytes())

    return destination_files


def run_refresh(*, dry_run: bool, now: datetime | None = None) -> tuple[RefreshOutcome, dict[str, object]]:
    refreshed_at = now or datetime.now(timezone.utc)
    if COLLECTION_PATH.exists():
        COLLECTION_PATH.unlink()
    registry = load_registry(PROJECT_ROOT / "automation" / "sources.json")
    client = BlizzardHttpClient(
        registry.allowed_hosts,
        registry.max_response_bytes,
        registry.timeout_seconds,
    )
    current_patch, documents = collect_official_documents(
        registry=registry,
        client=client,
    )

    source_directory = WORK_DIRECTORY / "sources"
    source_directory.mkdir(parents=True, exist_ok=True)
    for document in documents:
        suffix = ".json" if document.mime_type == "application/json" else ".html"
        (source_directory / f"{document.content_hash}{suffix}").write_bytes(
            document.body
        )
    COLLECTION_PATH.write_text(
        json.dumps(
            {
                "currentPatch": current_patch,
                "sourceUrls": sorted(
                    {document.url for document in documents}
                ),
                "documents": [
                    {
                        "url": document.url,
                        "contentHash": document.content_hash,
                        "channel": document.channel,
                        "patch": document.patch,
                        "publishedAt": document.published_at.isoformat(),
                    }
                    for document in documents
                ],
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    qualification = _qualify_documents(
        documents,
        current_patch,
        refreshed_at.date(),
    )
    english_document = build_english_document(
        qualification.accepted,
        refreshed_at.isoformat(),
    )
    base_terminology = json.loads(
        TERMINOLOGY_PATH.read_text(encoding="utf-8")
    )
    canonical_data = json.loads(
        (PROJECT_ROOT / "data" / "retail-patch-notes.json").read_text(
            encoding="utf-8",
        )
    )
    runtime_terminology = build_runtime_terminology(
        base_terminology,
        canonical_data,
    )
    RUNTIME_TERMINOLOGY_PATH.write_text(
        json.dumps(runtime_terminology, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    translate = lambda document: _translator(
        document,
        RUNTIME_TERMINOLOGY_PATH,
    )
    validate = lambda batch: _validator(
        batch,
        RUNTIME_TERMINOLOGY_PATH,
    )

    release_files = _release_files(PROJECT_ROOT)
    if dry_run:
        with TemporaryDirectory() as temporary_directory:
            temporary_files = _copy_release_files(
                release_files,
                Path(temporary_directory),
            )
            outcome = coordinate_release(
                files=temporary_files,
                english_document=english_document,
                current_patch=current_patch,
                release_date=refreshed_at.date(),
                translate=translate,
                validate=validate,
                refresh=_refresher,
            )
    else:
        outcome = coordinate_release(
            files=release_files,
            english_document=english_document,
            current_patch=current_patch,
            release_date=refreshed_at.date(),
            translate=translate,
            validate=validate,
            refresh=_refresher,
        )

    warning_summary = summarize_terminology_warnings(
        outcome.terminology_warnings
    )
    audit = {
        **asdict(outcome),
        "status": outcome.status.value,
        "dryRun": dry_run,
        "currentPatch": current_patch,
        "asOfDate": refreshed_at.date().isoformat(),
        "accepted": len(qualification.accepted),
        "terminologyWarningCount": warning_summary.total,
        "terminologyWarningsByLocale": warning_summary.by_locale,
        "rejected": [
            {"sourceUrl": item.change.source_url, "reason": item.reason}
            for item in qualification.rejected
        ],
        "sourceUrls": sorted({document.url for document in documents}),
    }

    return outcome, audit


def _write_result(audit: dict[str, object]) -> None:
    WORK_DIRECTORY.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect and prepare verified Blizzard Retail patch notes.",
    )
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()

    try:
        outcome, audit = run_refresh(dry_run=arguments.dry_run)
    except Exception as error:
        collection = {}
        if COLLECTION_PATH.exists():
            collection = json.loads(COLLECTION_PATH.read_text(encoding="utf-8"))
        outcome = RefreshOutcome(
            status=RefreshStatus.BLOCKED,
            reason=redact_secrets(str(error)),
        )
        audit = {
            **asdict(outcome),
            "status": outcome.status.value,
            "dryRun": arguments.dry_run,
            "sourceUrls": collection.get("sourceUrls", []),
            "currentPatch": collection.get("currentPatch", ""),
            "terminologyWarningCount": 0,
            "terminologyWarningsByLocale": {},
        }

    _write_result(audit)
    print(json.dumps(audit, ensure_ascii=False, sort_keys=True))

    return 1 if outcome.status == RefreshStatus.BLOCKED else 0


if __name__ == "__main__":
    raise SystemExit(main())
