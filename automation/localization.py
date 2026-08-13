from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from automation.extraction import (
    CLASS_NAMES,
    SPECIALIZATION_NAMES,
    _PatchHtmlParser,
    _format_leaf_path,
    _has_list_child,
    _structural_key,
)
from automation.models import ExtractedChange, SourceDocument


def _parse_blocks(document: SourceDocument):
    parser = _PatchHtmlParser()
    try:
        parser.feed(document.body.decode("utf-8"))
        parser.close()
    except UnicodeDecodeError as error:
        raise ValueError("localized article is not valid UTF-8") from error

    return parser.blocks


def _ancestor_indexes(blocks, index: int) -> list[int]:
    indexes: list[int] = []
    current: int | None = index
    while current is not None:
        block = blocks[current]
        if block.tag == "li":
            indexes.append(current)
        current = block.parent

    return list(reversed(indexes))


def _source_url(document: SourceDocument, original_url: str) -> str:
    fragment = urlsplit(original_url).fragment
    parsed = urlsplit(document.url)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, fragment)
    )


def _localized_heading(
    english_blocks,
    localized_blocks,
    leaf_index: int,
    heading: str,
) -> str:
    if not heading:
        return ""

    ancestor_indexes = _ancestor_indexes(english_blocks, leaf_index)
    for index in reversed(ancestor_indexes):
        if _structural_key(english_blocks[index].text) == heading.casefold():
            return localized_blocks[index].text

    for index in range(leaf_index - 1, -1, -1):
        if _structural_key(english_blocks[index].text) == heading.casefold():
            return localized_blocks[index].text

    raise ValueError(f"official article is missing heading: {heading}")


def _localized_bullet(
    english_blocks,
    localized_blocks,
    english_bullet: str,
    class_name: str,
    specialization: str,
) -> tuple[int, str]:
    matches: list[tuple[int, str]] = []
    for leaf_index, block in enumerate(english_blocks):
        if block.tag != "li" or _has_list_child(english_blocks, leaf_index):
            continue

        ancestor_indexes = _ancestor_indexes(english_blocks, leaf_index)
        structural_ancestors = [
            _structural_key(english_blocks[index].text)
            for index in ancestor_indexes
        ]
        ancestor_classes = [
            CLASS_NAMES[value]
            for value in structural_ancestors
            if value in CLASS_NAMES
        ]
        if ancestor_classes and ancestor_classes[-1] != class_name:
            continue
        if specialization:
            specializations = SPECIALIZATION_NAMES[class_name]
            ancestor_specializations = [
                specializations[value]
                for value in structural_ancestors
                if value in specializations
            ]
            if (
                ancestor_specializations
                and ancestor_specializations[-1] != specialization
            ):
                continue
        for start in range(len(ancestor_indexes)):
            english_path = [
                english_blocks[index].text
                for index in ancestor_indexes[start:]
            ]
            if _format_leaf_path(english_path) != english_bullet:
                continue

            localized_path = [
                localized_blocks[index].text
                for index in ancestor_indexes[start:]
            ]
            matches.append(
                (leaf_index, _format_leaf_path(localized_path))
            )

    unique = {(index, text) for index, text in matches}
    if len(unique) != 1:
        raise ValueError(
            "official article bullet alignment is missing or ambiguous"
        )

    return next(iter(unique))


def align_official_localizations(
    english_document: SourceDocument,
    localized_document: SourceDocument,
    changes: tuple[ExtractedChange, ...],
) -> tuple[ExtractedChange, ...]:
    english_blocks = _parse_blocks(english_document)
    localized_blocks = _parse_blocks(localized_document)
    english_structure = [
        (block.tag, block.parent, block.depth) for block in english_blocks
    ]
    localized_structure = [
        (block.tag, block.parent, block.depth) for block in localized_blocks
    ]
    if localized_structure != english_structure:
        raise ValueError("localized article structure does not match English")

    aligned: list[ExtractedChange] = []
    for change in changes:
        localized_bullets: list[str] = []
        leaf_indexes: list[int] = []
        for bullet in change.change:
            leaf_index, localized_bullet = _localized_bullet(
                english_blocks,
                localized_blocks,
                bullet,
                change.name,
                change.specialization,
            )
            leaf_indexes.append(leaf_index)
            localized_bullets.append(localized_bullet)

        if not leaf_indexes:
            raise ValueError("official localization has no aligned bullets")
        heading_index = leaf_indexes[0]
        aligned.append(
            ExtractedChange(
                channel=change.channel,
                category=change.category,
                effective_date=change.effective_date,
                patch=change.patch,
                name=_localized_heading(
                    english_blocks,
                    localized_blocks,
                    heading_index,
                    change.name,
                ),
                specialization=_localized_heading(
                    english_blocks,
                    localized_blocks,
                    heading_index,
                    change.specialization,
                ),
                change=tuple(localized_bullets),
                source_url=_source_url(localized_document, change.source_url),
            )
        )

    return tuple(aligned)
