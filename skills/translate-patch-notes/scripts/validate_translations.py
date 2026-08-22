from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
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
    r"^https://(?:news|worldofwarcraft|us\.forums)\.blizzard\.com/"
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
    "koKR": ("증가", "상향", "늘어", "커질"),
    "ptBR": ("aument", "maior", "mais"),
    "ruRU": ("увелич", "повыш", "возраст"),
    "zhCN": ("提高", "增加", "上调", "提升", "延长"),
    "zhTW": ("提高", "增加", "上調", "提升", "延長", "調高"),
}

DECREASE_MARKERS = {
    "deDE": ("verringer", "reduzier", "weniger", "gesenkt"),
    "esES": ("reduc", "reduj", "disminu", "menos"),
    "esMX": ("reduc", "reduj", "disminu", "menos"),
    "frFR": ("rédu", "diminu", "moins"),
    "itIT": ("ridott", "dimin", "meno"),
    "koKR": ("감소", "하향", "줄어"),
    "ptBR": ("reduz", "diminu", "menor", "menos"),
    "ruRU": ("уменьш", "сниж", "сократ"),
    "zhCN": ("降低", "减少", "下调", "削弱", "减免"),
    "zhTW": ("降低", "減少", "下調", "削弱", "縮短", "縮小"),
}

CONDITION_MARKERS = {
    "deDE": (
        "wenn", "während", "solange", "falls", "sofern", "nachdem",
        "bevor", "bei der verwendung", "beherrscht ihr", "ohne", "beim",
        "nach dem",
    ),
    "esES": (" si ", "cuando", "mientras", "siempre que", "después", "antes"),
    "esMX": (" si ", "cuando", "mientras", "siempre que", "después", "antes"),
    "frFR": (
        " si ", "lorsque", "quand", "pendant", "tant que", "après",
        "avant", "lors de", "à l’utilisation", "à l'utilisation",
        "tout en",
    ),
    "itIT": (
        " se ", "quando", "mentre", "finché", "dopo", "prima",
        "all'utilizzo", "sovracur", "lanciando",
    ),
    "koKR": ("경우", "때", "동안", "중", "후", "전", " 시 "),
    "ptBR": (
        " se ", "quando", "enquanto", "sempre que", "após", "antes",
        "ao ser", " ao ",
    ),
    "ruRU": (
        "если", "когда", "пока", "во время", "на время", " при ",
        "после", "до того",
    ),
    "zhCN": ("如果", "当", "时", "期间", "只要", "后", "前"),
    "zhTW": ("如果", "當", "時", "期間", "只要", "後", "前"),
}

SPANISH_CONDITION_MARKERS = {
    "if": (" si ", "en caso"),
    "when": ("cuando", " al "),
    "whenever": ("siempre que", "cada vez que"),
    "while": (
        "mientras",
        "durante",
        "a la vez que",
        "con el talento",
        "con la facultad",
        "con los talentos",
        "con las facultades",
        "bajo los efectos",
    ),
    "unless": ("a menos que", "salvo que"),
    "after": ("después", "tras"),
    "before": ("antes"),
}


@dataclass(frozen=True, slots=True)
class TranslationReport:
    validated_locales: tuple[str, ...]
    fallback_locales: tuple[str, ...]
    fallback_reasons: dict[str, str]
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


def _preserves_conditions(
    locale: str,
    english_text: str,
    localized_text: str,
) -> bool:
    condition_types = []
    for match in ENGLISH_CONDITION_PATTERN.finditer(english_text):
        trailing_text = english_text[match.end():]
        is_after_title = (
            match.group(0).casefold() == "after"
            and re.match(r"\s+the\s+[A-Z]", trailing_text) is not None
        )
        if not is_after_title:
            condition_types.append(match.group(0).casefold())
    if not condition_types:
        return True

    if locale in {"esES", "esMX"}:
        return all(
            _contains_marker(
                localized_text,
                SPANISH_CONDITION_MARKERS[condition_type],
            )
            for condition_type in condition_types
        )

    return _contains_marker(
        localized_text,
        CONDITION_MARKERS[locale],
    )


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

    if not _preserves_conditions(locale, english_text, localized_text):
        raise ValueError(
            f"{locale} bullet {bullet_number} loses a condition"
        )


def _validate_term(
    locale: str,
    english_term: str,
    localized_term: str,
    terminology: dict[str, object],
    uncertain_terms: set[str],
    protected_terms: set[str],
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

    if english_term in protected_terms and localized_term == english_term:
        return
    if require_verified and localized_term == english_term:
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
    semantic_approvals: set[int],
) -> None:
    trusted_canonical = localization.get("trustedCanonical") is True
    if localization.get("translatedFrom") != "en":
        raise ValueError(f"{locale} translatedFrom must be en")
    if localization.get("sourceUrl") != english.get("sourceUrl"):
        raise ValueError(f"{locale} must retain the en sourceUrl")

    _validate_terminology_urls(localization)
    raw_protected_terms = _require_list(
        localization.get("protectedTerms", []),
        f"{locale} protectedTerms",
    )
    protected_terms = {
        _require_string(term, f"{locale} protected term")
        for term in raw_protected_terms
    }
    english_content = "\n".join(
        (
            _require_string(english.get("name"), "en name"),
            _require_string(english.get("specialization"), "en specialization"),
            *(
                _require_string(change, "en change entry")
                for change in _require_list(english.get("change"), "en change")
            ),
        )
    )
    for term in protected_terms:
        if not term or term not in english_content or not term[0].isupper():
            raise ValueError(f"{locale} has an invalid protected term: {term}")

    terminology_locales = _require_dict(
        terminology.get("locales"),
        "terminology locales",
    )
    locale_terminology = _require_dict(
        terminology_locales.get(locale),
        f"terminology {locale}",
    )
    verified_terms = _require_dict(
        locale_terminology.get("terms"),
        f"terminology {locale} terms",
    )
    for term in protected_terms:
        if term not in verified_terms:
            raise ValueError(
                f"{locale} uses unverified terminology for {term}"
            )

    allow_agent_terminology = locale in {"ruRU", "zhCN"}
    _validate_term(
        locale,
        _require_string(english.get("name"), "en name"),
        _require_string(localization.get("name"), f"{locale} name"),
        terminology,
        uncertain_terms,
        protected_terms,
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
        protected_terms,
        require_verified=category == "Class",
    )

    english_changes = _require_list(english.get("change"), "en change")
    localized_changes = _require_list(
        localization.get("change"),
        f"{locale} change",
    )
    if len(english_changes) != len(localized_changes):
        raise ValueError(f"{locale} bullet count does not match en")

    raw_uncertain = localization.get("uncertainTerms", [])
    uncertain = _require_list(raw_uncertain, f"{locale} uncertainTerms")
    preserved_uncertain_terms = {
        _require_string(term, f"{locale} uncertain term")
        for term in uncertain
    }
    for term in preserved_uncertain_terms:
        if (
            not term
            or not term[0].isupper()
            or term not in english_content
            or term not in "\n".join(localized_changes)
        ):
            raise ValueError(f"{locale} has an invalid uncertain term: {term}")
    prose_exempt_terms = protected_terms | preserved_uncertain_terms

    for index, (english_change, localized_change) in enumerate(
        zip(english_changes, localized_changes, strict=True)
    ):
        english_text = _require_string(english_change, "en change entry")
        localized_text = _require_string(
            localized_change,
            f"{locale} change entry",
        )
        if allow_agent_terminology and not trusted_canonical:
            heading_terms = {
                _require_string(english.get("name"), "en name"),
                _require_string(
                    english.get("specialization"),
                    "en specialization",
                ),
            }
            checked_english_text = english_text
            checked_localized_text = localized_text
            for term in sorted(prose_exempt_terms, key=len, reverse=True):
                if term in english_text:
                    if term not in localized_text and term not in heading_terms:
                        raise ValueError(
                            f"{locale} bullet {index + 1} changes "
                            f"protected term: {term}"
                        )
                    checked_english_text = checked_english_text.replace(term, "")
                    if term in localized_text:
                        checked_localized_text = (
                            checked_localized_text.replace(term, "")
                        )
            english_words = {
                word.casefold()
                for word in re.findall(
                    r"[A-Za-z][A-Za-z'’\-]{2,}",
                    checked_english_text,
                )
            }
            localized_words = {
                word.casefold()
                for word in re.findall(
                    r"[A-Za-z][A-Za-z'’\-]{2,}",
                    checked_localized_text,
                )
            }
            leaked_words = english_words & localized_words
            if leaked_words:
                leaked = ", ".join(sorted(leaked_words))
                raise ValueError(
                    f"{locale} bullet {index + 1} contains English leakage: "
                    f"{leaked}"
                )
        if Counter(_numeric_tokens(english_text)) != Counter(
            _numeric_tokens(localized_text)
        ):
            raise ValueError(
                f"{locale} bullet {index + 1} changes numeric values"
            )
        if not trusted_canonical and index not in semantic_approvals:
            _validate_semantic_structure(
                locale,
                index + 1,
                english_text,
                localized_text,
            )

    uncertain_terms.update(
        f"{locale}: {term}" for term in preserved_uncertain_terms
    )


def validate_translation_batch(
    batch: object,
    terminology: object,
) -> TranslationReport:
    document = _require_dict(batch, "translation batch")
    terminology_document = _require_dict(terminology, "terminology")
    if terminology_document.get("schemaVersion") != 1:
        raise ValueError("unsupported terminology schemaVersion")

    changes = _require_list(document.get("changes"), "changes")
    raw_semantic_approvals = _require_list(
        document.get("semanticApprovals", []),
        "semanticApprovals",
    )
    semantic_approvals: set[tuple[int, str, int]] = set()
    for raw_approval in raw_semantic_approvals:
        approval = _require_dict(raw_approval, "semantic approval")
        change_index = approval.get("change")
        locale = approval.get("locale")
        bullet_index = approval.get("bullet")
        if (
            not isinstance(change_index, int)
            or isinstance(change_index, bool)
            or not isinstance(locale, str)
            or locale not in SUPPORTED_TRANSLATION_LOCALES
            or not isinstance(bullet_index, int)
            or isinstance(bullet_index, bool)
            or change_index < 0
            or bullet_index < 0
        ):
            raise ValueError("semantic approval has invalid coordinates")
        semantic_approvals.add((change_index, locale, bullet_index))

    validated_locales: set[str] = set()
    uncertain_terms: set[str] = set()
    consumed_semantic_approvals: set[tuple[int, str, int]] = set()

    for change_index, raw_change in enumerate(changes):
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

            approved_bullets = {
                bullet_index
                for approved_change, approved_locale, bullet_index
                in semantic_approvals
                if approved_change == change_index
                and approved_locale == locale
            }
            localized_changes = _require_list(
                localization.get("change"),
                f"{locale} change",
            )
            if any(
                bullet_index >= len(localized_changes)
                for bullet_index in approved_bullets
            ):
                raise ValueError("semantic approval bullet is out of range")

            _validate_agent_translation(
                locale,
                category,
                english,
                localization,
                terminology_document,
                uncertain_terms,
                approved_bullets,
            )
            consumed_semantic_approvals.update(
                approval
                for approval in semantic_approvals
                if approval[0] == change_index and approval[1] == locale
            )
            validated_locales.add(locale)

    if consumed_semantic_approvals != semantic_approvals:
        raise ValueError("semantic approval does not match an agent translation")

    fallback_locales = (
        set(SUPPORTED_TRANSLATION_LOCALES) - validated_locales
    )

    return TranslationReport(
        validated_locales=tuple(sorted(validated_locales)),
        fallback_locales=tuple(sorted(fallback_locales)),
        fallback_reasons={
            locale: "localization unavailable"
            for locale in sorted(fallback_locales)
        },
        uncertain_terms=tuple(sorted(uncertain_terms)),
    )


def classify_translation_batch(
    batch: object,
    terminology: object,
    target_locale: str | None = None,
) -> TranslationReport:
    document = _require_dict(batch, "translation batch")
    changes = _require_list(document.get("changes"), "changes")
    provided_fallback_reasons = _require_dict(
        document.get("fallbackReasons", {}),
        "fallbackReasons",
    )
    validated_locales: set[str] = set()
    fallback_reasons: dict[str, str] = {}
    uncertain_terms: set[str] = set()
    raw_semantic_approvals = _require_list(
        document.get("semanticApprovals", []),
        "semanticApprovals",
    )

    selected_locales = (
        {target_locale}
        if target_locale is not None
        else set(SUPPORTED_TRANSLATION_LOCALES)
    )
    unexpected_locales = selected_locales - set(
        SUPPORTED_TRANSLATION_LOCALES
    )
    if unexpected_locales:
        raise ValueError(
            "unsupported translation locale: "
            + ", ".join(sorted(unexpected_locales))
        )

    for locale in sorted(selected_locales):
        locale_is_complete = all(
            locale
            in _require_dict(
                _require_dict(raw_change, "change").get("localizations"),
                "localizations",
            )
            for raw_change in changes
        )
        if not locale_is_complete:
            raw_reason = provided_fallback_reasons.get(
                locale,
                "localization unavailable",
            )
            reason = _require_string(raw_reason, f"{locale} fallback reason")
            fallback_reasons[locale] = (
                reason.strip() or "localization unavailable"
            )
            continue

        locale_batch = deepcopy(document)
        locale_batch["semanticApprovals"] = [
            approval
            for approval in raw_semantic_approvals
            if _require_dict(approval, "semantic approval").get("locale")
            == locale
        ]
        for raw_change in locale_batch["changes"]:
            localizations = raw_change["localizations"]
            raw_change["localizations"] = {
                "en": localizations["en"],
                locale: localizations[locale],
            }

        try:
            report = validate_translation_batch(locale_batch, terminology)
        except ValueError as error:
            fallback_reasons[locale] = (
                "automatic validation failed: " + str(error)
            )
            continue

        validated_locales.add(locale)
        uncertain_terms.update(report.uncertain_terms)

    return TranslationReport(
        validated_locales=tuple(sorted(validated_locales)),
        fallback_locales=tuple(sorted(fallback_reasons)),
        fallback_reasons=fallback_reasons,
        uncertain_terms=tuple(sorted(uncertain_terms)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate grounded WoW patch-note translations.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--terminology", required=True, type=Path)
    parser.add_argument(
        "--locale",
        choices=sorted(SUPPORTED_TRANSLATION_LOCALES),
    )
    arguments = parser.parse_args()

    batch = json.loads(arguments.input.read_text(encoding="utf-8"))
    terminology = json.loads(
        arguments.terminology.read_text(encoding="utf-8")
    )
    report = classify_translation_batch(
        batch,
        terminology,
        target_locale=arguments.locale,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
