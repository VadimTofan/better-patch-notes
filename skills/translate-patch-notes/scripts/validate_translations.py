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
ENGLISH_INCREASE_PATTERN = re.compile(
    r"\b(?:increase|increased|increases|raised)\b",
    re.IGNORECASE,
)
ENGLISH_DECREASE_PATTERN = re.compile(
    r"\b(?:decrease|decreased|decreases|reduced|lowered)\b",
    re.IGNORECASE,
)
ENGLISH_CONDITION_PATTERN = re.compile(
    r"\b(?:if|when|whenever|while|unless|after|before)\b",
    re.IGNORECASE,
)

INCREASE_MARKERS = {
    "deDE": ("erhöh", "steiger", "mehr"),
    "esES": ("aument", "increment", "más"),
    "esMX": ("aument", "increment", "más"),
    "frFR": ("augment", "accru", "plus"),
    "itIT": ("aument", "increment", "più"),
    "koKR": ("증가", "상향", "늘어"),
    "ptBR": ("aument", "maior", "mais"),
    "ruRU": ("увелич", "повыш", "возраст"),
    "zhCN": ("提高", "增加", "上调", "提升"),
    "zhTW": ("提高", "增加", "上調", "提升"),
}

DECREASE_MARKERS = {
    "deDE": ("verringer", "reduzier", "weniger", "gesenkt"),
    "esES": ("reduc", "disminu", "menos"),
    "esMX": ("reduc", "disminu", "menos"),
    "frFR": ("rédu", "diminu", "moins"),
    "itIT": ("ridott", "dimin", "meno"),
    "koKR": ("감소", "하향", "줄어"),
    "ptBR": ("reduz", "diminu", "menor", "menos"),
    "ruRU": ("уменьш", "сниж", "сократ"),
    "zhCN": ("降低", "减少", "下调", "削弱"),
    "zhTW": ("降低", "減少", "下調", "削弱"),
}

CONDITION_MARKERS = {
    "deDE": ("wenn", "während", "solange", "falls", "sofern", "nachdem", "bevor"),
    "esES": (" si ", "cuando", "mientras", "siempre que", "después", "antes"),
    "esMX": (" si ", "cuando", "mientras", "siempre que", "después", "antes"),
    "frFR": (" si ", "lorsque", "quand", "pendant que", "tant que", "après", "avant"),
    "itIT": (" se ", "quando", "mentre", "finché", "dopo", "prima"),
    "koKR": ("경우", "때", "동안", "중", "후", "전"),
    "ptBR": (" se ", "quando", "enquanto", "sempre que", "após", "antes"),
    "ruRU": ("если", "когда", "пока", "во время", " при ", "после", "до того"),
    "zhCN": ("如果", "当", "时", "期间", "只要", "后", "前"),
    "zhTW": ("如果", "當", "時", "期間", "只要", "後", "前"),
}


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


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    padded_text = f" {text.casefold()} "

    return any(marker.casefold() in padded_text for marker in markers)


def _validate_semantic_structure(
    locale: str,
    bullet_number: int,
    english_text: str,
    localized_text: str,
) -> None:
    requires_increase = bool(ENGLISH_INCREASE_PATTERN.search(english_text))
    requires_decrease = bool(ENGLISH_DECREASE_PATTERN.search(english_text))
    has_increase = _contains_marker(
        localized_text,
        INCREASE_MARKERS[locale],
    )
    has_decrease = _contains_marker(
        localized_text,
        DECREASE_MARKERS[locale],
    )

    if (requires_increase and not has_increase) or (
        requires_decrease and not has_decrease
    ):
        raise ValueError(
            f"{locale} bullet {bullet_number} changes change direction"
        )

    if ENGLISH_CONDITION_PATTERN.search(english_text) and not _contains_marker(
        localized_text,
        CONDITION_MARKERS[locale],
    ):
        raise ValueError(
            f"{locale} bullet {bullet_number} loses a condition"
        )


def _validate_term(
    locale: str,
    english_term: str,
    localized_term: str,
    terminology: dict[str, object],
    uncertain_terms: set[str],
    require_verified: bool = False,
) -> None:
    if not english_term or english_term == "All":
        return

    locales = _require_dict(terminology.get("locales"), "terminology locales")
    locale_data = _require_dict(locales.get(locale), f"terminology {locale}")
    terms = _require_dict(locale_data.get("terms"), f"terminology {locale} terms")
    raw_entry = terms.get(english_term)
    if raw_entry is None:
        if require_verified:
            raise ValueError(
                f"{locale} uses unverified class terminology for "
                f"{english_term}"
            )
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
    category: str,
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
        require_verified=category == "Class",
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
        require_verified=category == "Class",
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
        _validate_semantic_structure(
            locale,
            index + 1,
            english_text,
            localized_text,
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
        category = _require_string(change.get("category"), "category")
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
                category,
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
