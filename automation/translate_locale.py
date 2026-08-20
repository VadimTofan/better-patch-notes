from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import replace
from datetime import date
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from automation.coordinator import SUPPORTED_TRANSLATION_LOCALES
from automation.runner import (
    PROJECT_ROOT,
    TRANSLATION_SCRIPT,
    VALIDATION_SCRIPT,
    _run,
)
from automation.reporting import redact_secrets


Generator = Callable[[dict[str, object], str, Path], dict[str, object]]
Validator = Callable[[dict[str, object], str, Path], tuple[str, ...]]
OfficialPreparer = Callable[[dict[str, object], str], None]


def _write_json(path: Path, document: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _prepare_official(
    document: dict[str, object],
    locale: str,
) -> None:
    from automation.http_client import BlizzardHttpClient
    from automation.runner import (
        _qualify_documents,
        add_official_localizations,
        collect_official_documents,
    )
    from automation.source_registry import load_registry

    registry = load_registry(PROJECT_ROOT / "automation" / "sources.json")
    selected_sources = tuple(
        source
        for source in registry.sources
        if source.kind == "version" or source.locale in {"en", locale}
    )
    selected_registry = replace(registry, sources=selected_sources)
    client = BlizzardHttpClient(
        selected_registry.allowed_hosts,
        selected_registry.max_response_bytes,
        selected_registry.timeout_seconds,
    )
    current_patch, source_documents = collect_official_documents(
        registry=selected_registry,
        client=client,
    )
    refreshed_date = date.fromisoformat(
        str(document["updatedAt"]).split("T", 1)[0]
    )
    qualification = _qualify_documents(
        source_documents,
        current_patch,
        refreshed_date,
    )
    add_official_localizations(
        document,
        qualification.accepted,
        source_documents,
    )


def _generate(
    document: dict[str, object],
    locale: str,
    terminology_path: Path,
) -> dict[str, object]:
    with TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        input_path = temporary_root / "english.json"
        output_path = temporary_root / "translated.json"
        _write_json(input_path, document)
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
                "--trusted-checkpoint",
                str(PROJECT_ROOT / "data" / "retail-patch-notes.json"),
                "--locale",
                locale,
            ],
            1200,
        )
        return json.loads(output_path.read_text(encoding="utf-8"))


def _validate(
    batch: dict[str, object],
    locale: str,
    terminology_path: Path,
) -> tuple[str, ...]:
    with TemporaryDirectory() as temporary_directory:
        batch_path = Path(temporary_directory) / "translation.json"
        _write_json(batch_path, batch)
        output = _run(
            [
                sys.executable,
                str(VALIDATION_SCRIPT),
                "--input",
                str(batch_path),
                "--terminology",
                str(terminology_path),
                "--locale",
                locale,
            ]
        )
    report = json.loads(output)
    if report.get("validated_locales") != [locale]:
        reasons = report.get("fallback_reasons", {})
        reason = reasons.get(locale, "locale validation was incomplete")
        raise ValueError(str(reason))

    return tuple(report.get("uncertain_terms", ()))


def translate_locale(
    *,
    locale: str,
    english_path: Path,
    terminology_path: Path,
    output_path: Path,
    prepare_official: OfficialPreparer = _prepare_official,
    generate: Generator = _generate,
    validate: Validator = _validate,
) -> int:
    if locale not in SUPPORTED_TRANSLATION_LOCALES:
        raise ValueError(f"unsupported translation locale: {locale}")

    document = json.loads(english_path.read_text(encoding="utf-8"))
    try:
        prepare_official(document, locale)
        batch = generate(document, locale, terminology_path)
        uncertain_terms = validate(batch, locale, terminology_path)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        _write_json(
            output_path,
            {
                "locale": locale,
                "status": "FAILED",
                "reason": redact_secrets(str(error)),
                "uncertainTerms": [],
            },
        )
        return 1

    _write_json(
        output_path,
        {
            "locale": locale,
            "status": "PASS",
            "reason": "",
            "uncertainTerms": list(uncertain_terms),
            "batch": batch,
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate and validate one patch-note locale.",
    )
    parser.add_argument(
        "--locale",
        required=True,
        choices=sorted(SUPPORTED_TRANSLATION_LOCALES),
    )
    parser.add_argument("--english", required=True, type=Path)
    parser.add_argument("--terminology", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    return translate_locale(
        locale=arguments.locale,
        english_path=arguments.english,
        terminology_path=arguments.terminology,
        output_path=arguments.output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
