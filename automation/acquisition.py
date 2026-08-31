from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Protocol

from automation.coordinator import build_english_document
from automation.models import ExtractedChange, RegisteredSource
from automation.release_files import has_meaningful_change


class RefreshResult(Protocol):
    added: int
    skipped: int
    promoted: int
    localized: int
    ambiguous: int
    removed: int


Refresher = Callable[[Path, Path, Path, str], RefreshResult]


def english_acquisition_sources(
    sources: tuple[RegisteredSource, ...],
) -> tuple[RegisteredSource, ...]:
    return tuple(
        source
        for source in sources
        if source.kind == "version" or source.locale == "en"
    )


@dataclass(frozen=True, slots=True)
class AcquisitionOutcome:
    status: str
    current_patch: str
    accepted: int
    added: int
    removed: int
    ambiguous: int
    reason: str


def _write_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare_acquisition(
    *,
    changes: tuple[ExtractedChange, ...],
    current_patch: str,
    refreshed_at: datetime,
    canonical_data_path: Path,
    canonical_lua_path: Path,
    output_directory: Path,
    refresh: Refresher,
) -> AcquisitionOutcome:
    """Prepare English-only artifacts without modifying release files."""
    output_directory.mkdir(parents=True, exist_ok=True)
    english_document = build_english_document(
        changes,
        refreshed_at.isoformat(),
    )
    english_path = output_directory / "english-document.json"
    _write_json(english_path, english_document)
    refresh_input = {
        "retrievedAt": english_document["updatedAt"],
        "changes": [
            {
                **change,
                "replacesSourceUrl": "",
            }
            for change in english_document["changes"]
        ],
    }
    refresh_input_path = output_directory / "english-refresh-input.json"
    _write_json(refresh_input_path, refresh_input)

    before = json.loads(canonical_data_path.read_text(encoding="utf-8"))
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        staged_data_path = temporary_root / canonical_data_path.name
        staged_lua_path = temporary_root / canonical_lua_path.name
        shutil.copyfile(canonical_data_path, staged_data_path)
        shutil.copyfile(canonical_lua_path, staged_lua_path)
        refresh_result = refresh(
            refresh_input_path,
            staged_data_path,
            staged_lua_path,
            current_patch,
        )
        after = json.loads(staged_data_path.read_text(encoding="utf-8"))

    ambiguous = refresh_result.ambiguous
    if ambiguous:
        status = "BLOCKED"
        reason = (
            f"English preflight produced {ambiguous} ambiguous "
            "records"
        )
    elif has_meaningful_change(before, after):
        status = "DATA_CHANGED"
        reason = ""
    else:
        status = "NO_CHANGE"
        reason = ""

    outcome = AcquisitionOutcome(
        status=status,
        current_patch=current_patch,
        accepted=len(changes),
        added=refresh_result.added,
        removed=refresh_result.removed,
        ambiguous=ambiguous,
        reason=reason,
    )
    _write_json(output_directory / "acquisition-result.json", asdict(outcome))

    return outcome


def run_acquisition(
    *,
    output_directory: Path,
    now: datetime | None = None,
) -> AcquisitionOutcome:
    from automation.runner import (
        PROJECT_ROOT,
        _qualify_documents,
        _refresher,
        build_runtime_terminology,
        collect_official_documents,
    )
    from automation.http_client import BlizzardHttpClient
    from automation.source_registry import load_registry

    refreshed_at = now or datetime.now(timezone.utc)
    registry = load_registry(PROJECT_ROOT / "automation" / "sources.json")
    registry = replace(
        registry,
        sources=english_acquisition_sources(registry.sources),
    )
    client = BlizzardHttpClient(
        registry.allowed_hosts,
        registry.max_response_bytes,
        registry.timeout_seconds,
    )
    current_patch, documents = collect_official_documents(
        registry=registry,
        client=client,
    )
    qualification = _qualify_documents(
        documents,
        current_patch,
        refreshed_at.date(),
    )

    canonical_data_path = PROJECT_ROOT / "data" / "retail-patch-notes.json"
    canonical_lua_path = PROJECT_ROOT / "PatchNotesData.lua"
    outcome = prepare_acquisition(
        changes=qualification.accepted,
        current_patch=current_patch,
        refreshed_at=refreshed_at,
        canonical_data_path=canonical_data_path,
        canonical_lua_path=canonical_lua_path,
        output_directory=output_directory,
        refresh=_refresher,
    )

    base_terminology = json.loads(
        (
            PROJECT_ROOT
            / "skills"
            / "translate-patch-notes"
            / "references"
            / "terminology.json"
        ).read_text(encoding="utf-8")
    )
    canonical_data = json.loads(
        canonical_data_path.read_text(encoding="utf-8")
    )
    runtime_terminology = build_runtime_terminology(
        base_terminology,
        canonical_data,
    )
    _write_json(
        output_directory / "runtime-terminology.json",
        runtime_terminology,
    )
    _write_json(
        output_directory / "collection.json",
        {
            "currentPatch": current_patch,
            "sourceUrls": sorted({document.url for document in documents}),
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
    )

    return outcome


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Acquire and compare official English patch notes.",
    )
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    from automation.reporting import redact_secrets

    try:
        outcome = run_acquisition(output_directory=arguments.output)
    except Exception as error:
        arguments.output.mkdir(parents=True, exist_ok=True)
        _write_json(
            arguments.output / "acquisition-result.json",
            {
                "status": "BLOCKED",
                "reason": redact_secrets(str(error)),
                "current_patch": "",
                "accepted": 0,
                "added": 0,
                "removed": 0,
            },
        )
        return 1

    return 0 if outcome.status in {"NO_CHANGE", "DATA_CHANGED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
