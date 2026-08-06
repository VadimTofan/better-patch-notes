from dataclasses import replace
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
import unittest


from automation.extraction import AmbiguousPatchNote, extract_changes
from automation.models import SourceDocument


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "blizzard"


def _document(fixture: str, channel: str = "ptr") -> SourceDocument:
    body = (FIXTURE_ROOT / fixture).read_bytes()

    return SourceDocument(
        url="https://us.forums.blizzard.com/en/wow/t/notes/1/18",
        channel=channel,
        patch="12.1.0" if channel == "ptr" else "current",
        locale="en",
        title="Official patch notes",
        author="Linxy",
        published_at=datetime(2026, 7, 31, 18, 49, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 31, 18, 55, tzinfo=timezone.utc),
        body=body,
        mime_type="text/html",
        content_hash=sha256(body).hexdigest(),
        author_is_blue=True,
    )


# Describe: strict conversion of Blizzard sections into refresh input
class PatchNoteExtractionTests(unittest.TestCase):
    def test_groups_multiple_bullets_into_one_change_array(self) -> None:
        # Given
        document = _document("class-notes.html")

        # When
        changes = extract_changes(document)

        # Then
        mage = next(
            change
            for change in changes
            if change.name == "Mage" and change.specialization == "Arcane"
        )
        self.assertEqual(
            mage.change,
            (
                "Arcane Blast damage increased by 20%.",
                "Arcane Barrage damage reduced by 3%.",
            ),
        )
        self.assertEqual(mage.category, "Class")
        self.assertEqual(mage.patch, "12.1.0")

    def test_excludes_a_pvp_only_class_bullet(self) -> None:
        # Given
        document = _document("class-notes.html")

        # When
        changes = extract_changes(document)

        # Then
        self.assertFalse(
            any(change.specialization == "Fire" for change in changes)
        )

    def test_preserves_dungeon_hierarchy_and_source_anchor(self) -> None:
        # Given
        document = _document("dungeon-notes.html")

        # When
        changes = extract_changes(document)

        # Then
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].category, "Dungeon")
        self.assertEqual(changes[0].name, "Ruby Life Pools")
        self.assertEqual(
            changes[0].change,
            (
                "Melidrussa Chillworn — Hailburst: Reduced damage by 10%.",
            ),
        )
        self.assertTrue(changes[0].source_url.endswith("#ruby-life-pools"))

    def test_maps_a_dungeon_update_general_section_to_all_dungeons(self) -> None:
        # Given
        document = replace(
            _document("dungeon-notes.html"),
            body=(
                b"<p><strong>Dungeon Update</strong></p>"
                b"<p><strong>General</strong></p>"
                b"<ul><li>Enemy forces tooltips were corrected.</li></ul>"
            ),
        )

        # When
        changes = extract_changes(document)

        # Then
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].name, "All Dungeons")

    def test_extracts_raid_changes_independently(self) -> None:
        # Given
        document = _document("raid-notes.html")

        # When
        changes = extract_changes(document)

        # Then
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].category, "Raid")
        self.assertEqual(changes[0].name, "The Venomous Abyss")
        self.assertEqual(
            changes[0].change,
            ("Imperator Averzian — Void Rupture: Damage reduced by 12%.",),
        )

    def test_stops_on_an_unknown_heading_inside_a_supported_section(self) -> None:
        # Given
        document = _document("class-notes.html")
        document = replace(
            document,
            body=b"<h2>CLASSES</h2><h3>Experimental Wizardry</h3>",
        )

        # When / Then
        with self.assertRaisesRegex(AmbiguousPatchNote, "heading"):
            extract_changes(document)

    def test_extracts_the_current_blizzard_hotfix_article_shape(self) -> None:
        # Given
        document = _document("live-hotfix-notes.html", channel="live")

        # When
        changes = extract_changes(document)

        # Then
        self.assertEqual(len(changes), 3)
        balance = next(change for change in changes if change.name == "Druid")
        self.assertEqual(balance.specialization, "Balance")
        self.assertEqual(balance.effective_date.isoformat(), "2026-08-04")
        dungeon = next(
            change for change in changes if change.name == "Ruby Life Pools"
        )
        self.assertEqual(dungeon.category, "Dungeon")
        raid = next(
            change for change in changes if change.name == "The Voidspire"
        )
        self.assertEqual(raid.category, "Raid")

    def test_ignores_unknown_instances_outside_the_requested_window(self) -> None:
        # Given
        document = replace(
            _document("live-hotfix-notes.html", channel="live"),
            body=(
                b"<p><strong>June 1, 2026</strong></p>"
                b"<p><strong>Dungeons and Raids</strong></p>"
                b"<ul><li>Retired Unknown Instance<ul>"
                b"<li>Old change.</li></ul></li></ul>"
                b"<p><strong>August 4, 2026</strong></p>"
                b"<p><strong>Classes</strong></p>"
                b"<ul><li>Druid<ul><li>Balance<ul>"
                b"<li>All damage increased by 4%.</li>"
                b"</ul></li></ul></li></ul>"
            ),
        )

        # When
        changes = extract_changes(
            document,
            earliest_date=date(2026, 7, 23),
            latest_date=date(2026, 8, 5),
        )

        # Then
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].name, "Druid")


if __name__ == "__main__":
    unittest.main()
