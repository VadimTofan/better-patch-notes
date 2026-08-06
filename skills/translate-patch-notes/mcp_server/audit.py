from __future__ import annotations

from collections import Counter
import re
from urllib.parse import urlparse


NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(\d+(?:[.,]\d+)?)(?:\s*(%))?"
)
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

CHECK_NAMES = (
    "record_present",
    "translation_type",
    "translated_from",
    "source_url",
    "terminology_urls",
    "bullet_count",
    "non_empty_bullets",
    "numeric_values",
    "encoding",
    "exact_english",
    "english_actions",
    "english_connectors",
    "english_number_words",
    "english_bugfix_phrase",
    "english_comparisons",
    "english_pronouns",
    "english_units",
    "english_3gram",
    "english_4gram",
    "english_5gram",
    "source_overlap",
    "name_localized",
    "specialization_localized",
    "heading_localized",
    "uncertain_terms_present",
    "uncertain_terms_scoped",
    "increase_direction",
    "decrease_direction",
    "condition_preservation",
    "regional_duplicate",
)

INCREASE_MARKERS = {
    "deDE": ("erhöh", "steiger", "mehr"),
    "esES": ("aument", "increment", "más"),
    "esMX": ("aument", "increment", "más"),
    "frFR": ("augment", "accru", "plus"),
    "itIT": ("aument", "increment", "più"),
    "koKR": ("증가", "상향"),
    "ptBR": ("aument", "maior", "mais"),
    "ruRU": ("увелич", "повыш"),
    "zhCN": ("提高", "增加", "上调"),
    "zhTW": ("提高", "增加", "上調"),
}

DECREASE_MARKERS = {
    "deDE": ("verringer", "reduzier", "weniger"),
    "esES": ("reduc", "disminu", "menos"),
    "esMX": ("reduc", "disminu", "menos"),
    "frFR": ("rédu", "diminu", "moins"),
    "itIT": ("ridott", "dimin", "meno"),
    "koKR": ("감소", "하향"),
    "ptBR": ("reduz", "diminu", "menos"),
    "ruRU": ("уменьш", "сниж"),
    "zhCN": ("降低", "减少", "下调"),
    "zhTW": ("降低", "減少", "下調"),
}

ENGLISH_GROUPS = {
    "english_actions": {
        "added", "changed", "damage", "fixed", "increased", "reduced",
    },
    "english_connectors": {"and", "because", "but", "from", "that", "with"},
    "english_number_words": {"first", "second", "three", "two", "one"},
    "english_bugfix_phrase": {"issue", "incorrectly", "prevented"},
    "english_comparisons": {"higher", "less", "lower", "more", "than"},
    "english_pronouns": {"their", "them", "they", "this", "your"},
    "english_units": {"minutes", "seconds", "yards"},
}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item for item in value if isinstance(item, str)]


def _numeric_tokens(text: str) -> tuple[str, ...]:
    return tuple(
        number.replace(",", ".") + percent
        for number, percent in NUMBER_PATTERN.findall(text)
    )


def _english_tokens(text: str) -> list[str]:
    return [token.lower() for token in WORD_PATTERN.findall(text)]


def _mask_uncertain(text: str, uncertain_terms: list[str]) -> str:
    masked = text
    for term in sorted(uncertain_terms, key=len, reverse=True):
        if term:
            masked = re.sub(re.escape(term), " ", masked, flags=re.IGNORECASE)
    return masked


def _has_shared_ngram(source: str, target: str, size: int) -> bool:
    source_tokens = _english_tokens(source)
    target_tokens = _english_tokens(target)
    source_ngrams = {
        tuple(source_tokens[index : index + size])
        for index in range(len(source_tokens) - size + 1)
    }
    return any(
        tuple(target_tokens[index : index + size]) in source_ngrams
        for index in range(len(target_tokens) - size + 1)
    )


def _is_blizzard_url(value: object) -> bool:
    if not isinstance(value, str):
        return False

    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname
        in {"news.blizzard.com", "worldofwarcraft.blizzard.com"}
    )


def _matches_terminology(
    english_term: object,
    localized_term: object,
    terminology: dict[str, object],
    uncertain_terms: list[str],
) -> bool:
    if not isinstance(english_term, str) or not english_term:
        return True
    if english_term == "All":
        return True

    entry = terminology.get(english_term)
    if isinstance(entry, dict):
        return localized_term == entry.get("localized")

    return localized_term == english_term and english_term in uncertain_terms


def audit_translation(
    locale: str,
    english: dict[str, object],
    localized: dict[str, object],
    regional_peer: dict[str, object] | None = None,
    terminology: dict[str, object] | None = None,
) -> dict[str, object]:
    """Run a deterministic 30-check review of one localized record."""

    results = {name: True for name in CHECK_NAMES}
    english_changes = _strings(english.get("change"))
    localized_changes = _strings(localized.get("change"))
    uncertain_terms = _strings(localized.get("uncertainTerms", []))
    translation_type = localized.get("translationType")

    results["record_present"] = bool(localized)
    results["translation_type"] = translation_type in {"official", "agent"}
    results["translated_from"] = (
        translation_type == "official"
        or localized.get("translatedFrom") == "en"
    )
    results["source_url"] = (
        _is_blizzard_url(localized.get("sourceUrl"))
        if translation_type == "official"
        else localized.get("sourceUrl") == english.get("sourceUrl")
    )
    terminology_urls = localized.get("terminologySourceUrls")
    results["terminology_urls"] = (
        translation_type == "official"
        or (
            isinstance(terminology_urls, list)
            and bool(terminology_urls)
            and all(_is_blizzard_url(url) for url in terminology_urls)
        )
    )
    results["bullet_count"] = (
        len(english_changes) == len(localized_changes)
        and isinstance(localized.get("change"), list)
    )
    results["non_empty_bullets"] = bool(localized_changes) and all(
        change.strip() for change in localized_changes
    )
    results["numeric_values"] = (
        len(english_changes) == len(localized_changes)
        and all(
            Counter(_numeric_tokens(source)) == Counter(_numeric_tokens(target))
            for source, target in zip(
                english_changes,
                localized_changes,
                strict=True,
            )
        )
    )

    localized_text = "\n".join(localized_changes)
    english_text = "\n".join(english_changes)
    masked_text = _mask_uncertain(localized_text, uncertain_terms)
    results["encoding"] = not any(
        marker in localized_text for marker in ("�", "Ã", "Â", "â€")
    )
    results["exact_english"] = localized_text.strip() != english_text.strip()

    localized_words = set(_english_tokens(masked_text))
    for check_name, words in ENGLISH_GROUPS.items():
        results[check_name] = not bool(localized_words & words)

    results["english_3gram"] = not _has_shared_ngram(
        english_text,
        masked_text,
        3,
    )
    results["english_4gram"] = not _has_shared_ngram(
        english_text,
        masked_text,
        4,
    )
    results["english_5gram"] = not _has_shared_ngram(
        english_text,
        masked_text,
        5,
    )
    source_tokens = set(_english_tokens(english_text))
    target_tokens = set(_english_tokens(masked_text))
    overlap = len(source_tokens & target_tokens) / max(1, len(source_tokens))
    results["source_overlap"] = overlap < 0.5

    english_name = english.get("name")
    localized_name = localized.get("name")
    english_specialization = english.get("specialization")
    localized_specialization = localized.get("specialization")
    if translation_type == "agent" and terminology is not None:
        results["name_localized"] = _matches_terminology(
            english_name,
            localized_name,
            terminology,
            uncertain_terms,
        )
        results["specialization_localized"] = _matches_terminology(
            english_specialization,
            localized_specialization,
            terminology,
            uncertain_terms,
        )
    else:
        results["name_localized"] = (
            not english_name
            or localized_name != english_name
            or english_name in uncertain_terms
        )
        results["specialization_localized"] = (
            not english_specialization
            or english_specialization == "All"
            or localized_specialization != english_specialization
            or english_specialization in uncertain_terms
        )
    results["heading_localized"] = bool(localized_name) and bool(
        localized_specialization
    )
    results["uncertain_terms_present"] = all(
        term in localized_text
        or term == localized_name
        or term == localized_specialization
        for term in uncertain_terms
    )
    results["uncertain_terms_scoped"] = all(
        term.strip() and len(term.split()) <= 5 for term in uncertain_terms
    )

    lowered_english = english_text.lower()
    lowered_localized = localized_text.lower()
    if any(word in lowered_english for word in ("increase", "increased")):
        results["increase_direction"] = any(
            marker in lowered_localized
            for marker in INCREASE_MARKERS.get(locale, ())
        )
    if any(word in lowered_english for word in ("decrease", "reduced")):
        results["decrease_direction"] = any(
            marker in lowered_localized
            for marker in DECREASE_MARKERS.get(locale, ())
        )
    if any(word in lowered_english for word in (" if ", " when ", " while ")):
        results["condition_preservation"] = len(localized_text.split()) >= 3

    if regional_peer is not None:
        peer_changes = _strings(regional_peer.get("change"))
        both_official = (
            translation_type == "official"
            and regional_peer.get("translationType") == "official"
        )
        results["regional_duplicate"] = (
            both_official or localized_changes != peer_changes
        )

    findings = [
        {
            "check": name,
            "message": f"{name.replace('_', ' ')} check failed",
        }
        for name in CHECK_NAMES
        if not results[name]
    ]
    return {
        "locale": locale,
        "passed": not findings,
        "checks": [
            {"name": name, "passed": results[name]} for name in CHECK_NAMES
        ],
        "findings": findings,
    }
