from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit, urlunsplit

from automation.models import ExtractedChange, SourceDocument


CLASS_SPECIALIZATIONS = {
    "Death Knight": {"Blood", "Frost", "Unholy"},
    "Demon Hunter": {"Devourer", "Havoc", "Vengeance"},
    "Druid": {"Balance", "Feral", "Guardian", "Restoration"},
    "Evoker": {"Augmentation", "Devastation", "Preservation"},
    "Hunter": {"Beast Mastery", "Marksmanship", "Survival"},
    "Mage": {"Arcane", "Fire", "Frost"},
    "Monk": {"Brewmaster", "Mistweaver", "Windwalker"},
    "Paladin": {"Holy", "Protection", "Retribution"},
    "Priest": {"Discipline", "Holy", "Shadow"},
    "Rogue": {"Assassination", "Outlaw", "Subtlety"},
    "Shaman": {"Elemental", "Enhancement", "Restoration"},
    "Warlock": {"Affliction", "Demonology", "Destruction"},
    "Warrior": {"Arms", "Fury", "Protection"},
}
CLASS_NAMES = {name.casefold(): name for name in CLASS_SPECIALIZATIONS}
SPECIALIZATION_NAMES = {
    class_name: {name.casefold(): name for name in specializations}
    for class_name, specializations in CLASS_SPECIALIZATIONS.items()
}
DUNGEONS = {
    "All Dungeons",
    "Altar of Fangs",
    "Den of Nalorakk",
    "Kings' Rest",
    "Kings’ Rest",
    "Murder Row",
    "Ruby Life Pools",
    "Temple of Sethraliss",
    "The Blinding Vale",
    "Voidscar Arena",
}
RAIDS = {
    "Sporefall",
    "The Voidspire",
    "The Venomous Abyss",
}
INSTANCE_NAMES = {
    name.casefold(): name for name in DUNGEONS | RAIDS
}
SECTION_NAMES = {
    "classes": "Class",
    "class changes": "Class",
    "dungeons": "Dungeon",
    "dungeon changes": "Dungeon",
    "dungeon update": "Dungeon",
    "dungeons and raids": "Instance",
    "raid": "Raid",
    "raids": "Raid",
    "raid changes": "Raid",
}
BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}


class AmbiguousPatchNote(ValueError):
    """A qualifying section cannot be represented without guessing."""


@dataclass(slots=True)
class _Block:
    tag: str
    parent: int | None
    depth: int
    anchor: str
    parts: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join("".join(self.parts).split())


class _PatchHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_Block] = []
        self._open_blocks: list[tuple[str, int]] = []

    def handle_starttag(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag not in BLOCK_TAGS:
            return

        parent = next(
            (
                index
                for open_tag, index in reversed(self._open_blocks)
                if open_tag == "li"
            ),
            None,
        )
        depth = sum(
            1 for open_tag, _ in self._open_blocks if open_tag == "li"
        )
        if normalized_tag == "li":
            depth += 1

        attribute_map = dict(attributes)
        block = _Block(
            tag=normalized_tag,
            parent=parent,
            depth=depth,
            anchor=(attribute_map.get("id") or "").strip(),
        )
        self.blocks.append(block)
        self._open_blocks.append((normalized_tag, len(self.blocks) - 1))

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        for position in range(len(self._open_blocks) - 1, -1, -1):
            if self._open_blocks[position][0] == normalized_tag:
                del self._open_blocks[position:]
                return

    def handle_data(self, data: str) -> None:
        if self._open_blocks:
            self.blocks[self._open_blocks[-1][1]].parts.append(data)


def _source_with_anchor(url: str, anchor: str) -> str:
    if not anchor:
        return url

    parsed = urlsplit(url)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.query, anchor)
    )


def _list_ancestors(blocks: list[_Block], index: int) -> list[_Block]:
    ancestors: list[_Block] = []
    current: int | None = index
    while current is not None:
        block = blocks[current]
        if block.tag == "li":
            ancestors.append(block)
        current = block.parent

    return list(reversed(ancestors))


def _has_list_child(blocks: list[_Block], index: int) -> bool:
    return any(block.parent == index for block in blocks)


def _format_leaf_path(path: list[str]) -> str:
    cleaned = [text.strip() for text in path if text.strip()]
    if not cleaned:
        raise AmbiguousPatchNote("empty bullet path")
    if len(cleaned) == 1:
        return cleaned[0]

    return f"{' — '.join(cleaned[:-1])}: {cleaned[-1]}"


def _is_pvp_only(text: str) -> bool:
    normalized = text.casefold()
    return (
        "in pvp combat" in normalized
        and "does not apply to pvp combat" not in normalized
    )


def _heading_section(text: str) -> str | None:
    normalized = re.sub(r"\s+", " ", text.strip()).casefold()
    return SECTION_NAMES.get(normalized)


def _effective_date(text: str) -> date | None:
    normalized = " ".join(text.split())
    try:
        return datetime.strptime(normalized, "%B %d, %Y").date()
    except ValueError:
        return None


def extract_changes(
    document: SourceDocument,
    *,
    earliest_date: date | None = None,
    latest_date: date | None = None,
) -> tuple[ExtractedChange, ...]:
    if not document.author_is_blue:
        raise AmbiguousPatchNote("source author is not verified as Blizzard")

    parser = _PatchHtmlParser()
    try:
        parser.feed(document.body.decode("utf-8"))
        parser.close()
    except UnicodeDecodeError as error:
        raise AmbiguousPatchNote("source body is not valid UTF-8") from error

    blocks = parser.blocks
    grouped: dict[tuple[str, str, str, str, date], list[str]] = {}
    section: str | None = None
    section_anchor = ""
    context_name = ""
    context_anchor = ""
    current_date = document.published_at.date()

    def date_is_requested() -> bool:
        return (
            (earliest_date is None or current_date >= earliest_date)
            and (latest_date is None or current_date <= latest_date)
        )

    for index, block in enumerate(blocks):
        text = block.text
        if not text:
            continue

        parsed_date = _effective_date(text)
        if block.tag == "p" and parsed_date is not None:
            current_date = parsed_date
            section = None
            context_name = ""
            context_anchor = ""
            continue

        candidate_section = _heading_section(text)
        if block.tag == "h2" or (
            block.tag == "p" and candidate_section is not None
        ):
            section = candidate_section
            section_anchor = block.anchor
            context_name = ""
            context_anchor = ""
            continue
        if section is None:
            continue

        if section == "Class" and block.tag in {"h3", "h4", "p"}:
            canonical_class = CLASS_NAMES.get(text.casefold())
            if canonical_class is not None:
                context_name = canonical_class
                context_anchor = block.anchor or section_anchor
                continue
            if block.tag in {"h3", "h4"}:
                if not date_is_requested():
                    continue
                raise AmbiguousPatchNote(
                    f"unknown class heading: {text}",
                )
        elif section in {"Dungeon", "Raid", "Instance"} and block.tag == "h3":
            context_name = text
            context_anchor = block.anchor or section_anchor
            continue
        elif (
            section == "Dungeon"
            and block.tag == "p"
            and text.casefold() in INSTANCE_NAMES
        ):
            context_name = INSTANCE_NAMES[text.casefold()]
            context_anchor = block.anchor or section_anchor
            continue
        elif (
            section == "Dungeon"
            and block.tag == "p"
            and text.casefold() == "general"
        ):
            context_name = "All Dungeons"
            context_anchor = block.anchor or section_anchor
            continue

        if block.tag != "li" or _has_list_child(blocks, index):
            continue
        if not date_is_requested():
            continue
        ancestors = _list_ancestors(blocks, index)
        path = [ancestor.text for ancestor in ancestors]
        specialization = ""
        if section == "Class":
            class_positions = [
                (position, CLASS_NAMES[value.casefold()])
                for position, value in enumerate(path)
                if value.casefold() in CLASS_NAMES
            ]
            if class_positions:
                class_position, context_name = class_positions[0]
                context_anchor = section_anchor
                path = path[class_position + 1 :]
            elif not context_name:
                if not class_positions:
                    raise AmbiguousPatchNote(
                        "class bullet has no recognized class",
                    )
            specifications = SPECIALIZATION_NAMES[context_name]
            specification_positions = [
                (position, specifications[value.casefold()])
                for position, value in enumerate(path)
                if value.casefold() in specifications
            ]
            if specification_positions:
                position, specialization = specification_positions[0]
                path = path[position + 1 :]
            if not path:
                continue
        elif section in {"Dungeon", "Raid", "Instance"}:
            instance_positions = [
                (position, INSTANCE_NAMES[value.casefold()])
                for position, value in enumerate(path)
                if value.casefold() in INSTANCE_NAMES
            ]
            if instance_positions:
                instance_position, context_name = instance_positions[0]
                context_anchor = section_anchor
                path = path[instance_position + 1 :]
            elif not context_name or section == "Instance":
                raise AmbiguousPatchNote("instance bullet has no name")
            if not path:
                continue

        category = section
        if section == "Instance":
            if context_name in DUNGEONS:
                category = "Dungeon"
            elif context_name in RAIDS:
                category = "Raid"
            else:
                raise AmbiguousPatchNote(
                    f"unknown dungeon or raid heading: {context_name}",
                )

        rendered_change = _format_leaf_path(path)
        if _is_pvp_only(rendered_change):
            continue

        source_url = _source_with_anchor(
            document.url,
            context_anchor or section_anchor,
        )
        key = (
            category,
            context_name,
            specialization,
            source_url,
            current_date,
        )
        grouped.setdefault(key, []).append(rendered_change)

    changes = [
        ExtractedChange(
            channel=document.channel,
            category=category,
            effective_date=effective_date,
            patch=document.patch,
            name=name,
            specialization=specialization,
            change=tuple(change_texts),
            source_url=source_url,
        )
        for (
            category,
            name,
            specialization,
            source_url,
            effective_date,
        ), change_texts in grouped.items()
    ]

    return tuple(
        sorted(
            changes,
            key=lambda item: (
                item.category,
                item.name,
                item.specialization,
                item.source_url,
            ),
        )
    )
