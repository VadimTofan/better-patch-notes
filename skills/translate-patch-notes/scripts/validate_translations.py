from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re


SUPPORTED_TRANSLATION_LOCALES = (
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
)

NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(\d+(?:[.,]\d+)?)(?:\s*(%))?"
)
BLIZZARD_URL_PATTERN = re.compile(
    r"^https://(?:news|worldofwarcraft)\.blizzard\.com/"
)


@dataclass(frozen=True, slots=True)
class TranslationReport:
    validated_locales: tuple[str, ...]
    fallback_locales: tuple[str, ...]
    uncertain_terms: tuple[str, ...]


def _require_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")

    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")

    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")

    return value


def _numeric_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        number.replace(",", ".") + percent
        for number, percent in NUMBER_PATTERN.findall(text)
    )


def _validate_terminology_urls(localization: dict[str, object]) -> None:
    urls = _require_list(
        localization.get("terminologySourceUrls"),
        "terminologySourceUrls",
    )
    if not urls:
        raise ValueError("terminologySourceUrls must not be empty")

    for value in urls:
        url = _require_string(value, "terminologySourceUrls entry")
        if not BLIZZARD_URL_PATTERN.match(url):
            raise ValueError(
                "terminologySourceUrls must contain direct Blizzard URLs"
            )


def _validate_term(
    locale: str,
    english_term: str,
    localized_term: str,
    terminology: dict[str, object],
    uncertain_terms: set[str],
) -> None:
    if not english_term or english_term == "All":
        return

    locales = _require_dict(terminology.get("locales"), "terminology locales")
    locale_data = _require_dict(locales.get(locale), f"terminology {locale}")
    terms = _require_dict(locale_data.get("terms"), f"terminology {locale} terms")
    raw_entry = terms.get(english_term)
    if raw_entry is None:
        if localized_term != english_term:
            raise ValueError(
                f"{locale} uses unverified terminology for {english_term}"
            )
        uncertain_terms.add(f"{locale}: {english_term}")
        return

    entry = _require_dict(raw_entry, f"terminology {locale} {english_term}")
    expected = _require_string(entry.get("localized"), "localized term")
    if localized_term != expected:
        raise ValueError(
            f"{locale} {english_term} expected {expected}, got {localized_term}"
        )


def _validate_agent_translation(
    locale: str,
    english: dict[str, object],
    localization: dict[str, object],
    terminology: dict[str, object],
    uncertain_terms: set[str],
) -> None:
    if localization.get("translatedFrom") != "en":
        raise ValueError(f"{locale} translatedFrom must be en")
    if localization.get("sourceUrl") != english.get("sourceUrl"):
        raise ValueError(f"{locale} must retain the en sourceUrl")

    _validate_terminology_urls(localization)
    _validate_term(
        locale,
        _require_string(english.get("name"), "en name"),
        _require_string(localization.get("name"), f"{locale} name"),
        terminology,
        uncertain_terms,
    )
    _validate_term(
        locale,
        _require_string(english.get("specialization"), "en specialization"),
        _require_string(
            localization.get("specialization"),
            f"{locale} specialization",
        ),
        terminology,
        uncertain_terms,
    )

    english_changes = _require_list(english.get("change"), "en change")
    localized_changes = _require_list(
        localization.get("change"),
        f"{locale} change",
    )
    if len(english_changes) != len(localized_changes):
        raise ValueError(f"{locale} bullet count does not match en")

    for index, (english_change, localized_change) in enumerate(
        zip(english_changes, localized_changes, strict=True)
    ):
        english_text = _require_string(english_change, "en change entry")
        localized_text = _require_string(
            localized_change,
            f"{locale} change entry",
        )
        if Counter(_numeric_tokens(english_text)) != Counter(
            _numeric_tokens(localized_text)
        ):
            raise ValueError(
                f"{locale} bullet {index + 1} changes numeric values"
            )

    raw_uncertain = localization.get("uncertainTerms", [])
    for raw_term in _require_list(raw_uncertain, f"{locale} uncertainTerms"):
        term = _require_string(raw_term, f"{locale} uncertain term")
        if not any(
            term in _require_string(change, f"{locale} change entry")
            for change in localized_changes
        ):
            raise ValueError(
                f"{locale} uncertain term must remain in the translated text"
            )
        uncertain_terms.add(f"{locale}: {term}")


def validate_translation_batch(
    batch: object,
    terminology: object,
) -> TranslationReport:
    document = _require_dict(batch, "translation batch")
    terminology_document = _require_dict(terminology, "terminology")
    if terminology_document.get("schemaVersion") != 1:
        raise ValueError("unsupported terminology schemaVersion")

    changes = _require_list(document.get("changes"), "changes")
    validated_locales: set[str] = set()
    uncertain_terms: set[str] = set()

    for raw_change in changes:
        change = _require_dict(raw_change, "change")
        localizations = _require_dict(
            change.get("localizations"),
            "localizations",
        )
        english = _require_dict(localizations.get("en"), "en localization")
        if english.get("translationType") != "official":
            raise ValueError("en translationType must be official")

        for locale, raw_localization in localizations.items():
            if locale == "en":
                continue
            if locale not in SUPPORTED_TRANSLATION_LOCALES:
                raise ValueError(f"unsupported translation locale: {locale}")

            localization = _require_dict(raw_localization, f"{locale} localization")
            translation_type = localization.get("translationType")
            if translation_type == "official":
                validated_locales.add(locale)
                continue
            if translation_type != "agent":
                raise ValueError(
                    f"{locale} translationType must be official or agent"
                )

            _validate_agent_translation(
                locale,
                english,
                localization,
                terminology_document,
                uncertain_terms,
            )
            validated_locales.add(locale)

    fallback_locales = (
        set(SUPPORTED_TRANSLATION_LOCALES) - validated_locales
    )

    return TranslationReport(
        validated_locales=tuple(sorted(validated_locales)),
        fallback_locales=tuple(sorted(fallback_locales)),
        uncertain_terms=tuple(sorted(uncertain_terms)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate grounded WoW patch-note translations.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--terminology", required=True, type=Path)
    arguments = parser.parse_args()

    batch = json.loads(arguments.input.read_text(encoding="utf-8"))
    terminology = json.loads(
        arguments.terminology.read_text(encoding="utf-8")
    )
    report = validate_translation_batch(batch, terminology)
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
