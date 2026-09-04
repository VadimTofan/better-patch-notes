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

    def test_skips_general_class_section_notes_without_a_class(self) -> None:
        # Given Blizzard places a general tuning note before class headings
        document = replace(
            _document("class-notes.html"),
            body=(
                b"<h2>Classes</h2><ul>"
                b"<li>Player health and enemy damage increased globally.</li>"
                b"<li>Mage<ul><li>Arcane<ul>"
                b"<li>Arcane Blast damage increased by 20%.</li>"
                b"</ul></li></ul></li></ul>"
            ),
        )

        # When class changes are extracted
        changes = extract_changes(document)

        # Then the unscoped note is excluded and the class note remains
        self.assertEqual(1, len(changes))
        self.assertEqual("Mage", changes[0].name)
        self.assertEqual("Arcane", changes[0].specialization)

    def test_skips_nested_explanation_for_a_general_class_note(self) -> None:
        # Given Blizzard nests a developer explanation under a general note
        document = replace(
            _document("class-notes.html"),
            body=(
                b"<h2>Classes</h2><ul>"
                b"<li>Player health increased globally."
                b"<ul><li>Developers' notes: This applies to everyone.</li>"
                b"</ul></li>"
                b"<li>Mage<ul><li>Arcane<ul>"
                b"<li>Arcane Blast damage increased by 20%.</li>"
                b"</ul></li></ul></li></ul>"
            ),
        )

        # When class changes are extracted
        changes = extract_changes(document)

        # Then the complete unscoped note is excluded
        self.assertEqual(1, len(changes))
        self.assertEqual("Mage", changes[0].name)
        self.assertEqual("Arcane", changes[0].specialization)

    def test_recognizes_a_class_prefixed_by_a_disclosure_glyph(self) -> None:
        # Given Blizzard prefixes a collapsible class label with a glyph
        document = replace(
            _document("class-notes.html"),
            body=(
                b"<h2>Classes</h2><ul><li>\xe2\x96\xb6 Mage<ul>"
                b"<li>Arcane<ul>"
                b"<li>Arcane Blast damage increased by 20%.</li>"
                b"</ul></li></ul></li></ul>"
            ),
        )

        # When class changes are extracted
        changes = extract_changes(document)

        # Then the glyph is ignored only for structural label matching
        self.assertEqual(1, len(changes))
        self.assertEqual("Mage", changes[0].name)
        self.assertEqual("Arcane", changes[0].specialization)

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

    def test_recognizes_blizzard_dungeon_intro_sentence(self) -> None:
        # Given
        document = replace(
            _document("dungeon-notes.html"),
            body=(
                b"<p>We have made the following changes to dungeons:</p>"
                b"<p><strong>Altar of Fangs</strong></p>"
                b"<ul><li>General<ul>"
                b"<li>Removed a Ravenous Descendant.</li>"
                b"</ul></li></ul>"
            ),
        )

        # When
        changes = extract_changes(document)

        # Then
        self.assertEqual(1, len(changes))
        self.assertEqual("Dungeon", changes[0].category)
        self.assertEqual("Altar of Fangs", changes[0].name)
        self.assertEqual(
            ("General: Removed a Ravenous Descendant.",),
            changes[0].change,
        )

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

    def test_extracts_august_18_live_class_tuning_from_forum_shape(self) -> None:
        # Given Blizzard puts the effective date in the tuning topic title
        document = replace(
            _document("class-notes.html", channel="live"),
            title="Class Tuning Incoming – August 18",
            published_at=datetime(
                2026,
                8,
                15,
                0,
                11,
                tzinfo=timezone.utc,
            ),
            body=(
                b"<h1><strong>CLASS CHANGES</strong></h1>"
                b"<ul><li><h3><strong>MAGE</strong></h3><ul>"
                b"<li><strong>Arcane</strong><ul>"
                b"<li>All ability damage increased by 3%.</li>"
                b"</ul></li></ul></li></ul>"
                b"<h1><strong>PLAYER VERSUS PLAYER</strong></h1>"
                b"<ul><li><h3><strong>MAGE</strong></h3><ul>"
                b"<li><strong>Fire</strong><ul>"
                b"<li>Pyroblast damage increased by 10% in PvP combat.</li>"
                b"</ul></li></ul></li></ul>"
            ),
        )

        # When the reviewed live forum shape is extracted
        changes = extract_changes(document)

        # Then only PvE tuning is retained with its announced effective date
        self.assertEqual(1, len(changes))
        self.assertEqual("Mage", changes[0].name)
        self.assertEqual("Arcane", changes[0].specialization)
        self.assertEqual(date(2026, 8, 18), changes[0].effective_date)

    def test_extracts_a_named_raid_encounter_tuning_topic(self) -> None:
        # Given Blizzard publishes a raid hotfix without a Raid heading
        document = replace(
            _document("class-notes.html", channel="live"),
            title="Nymrissa Wavecaller Tuning Changes",
            published_at=datetime(
                2026,
                8,
                23,
                1,
                22,
                tzinfo=timezone.utc,
            ),
            body=(
                b"<p>We just sent a hotfix with the following changes to "
                b"Nymrissa Wavecaller on Mythic difficulty:</p>"
                b"<ul>"
                b"<li>Abyssal Rain's initial damage reduced by 12.5% on "
                b"Mythic difficulty</li>"
                b"<li>Frost Burst damage reduced by 40%</li>"
                b"</ul>"
            ),
        )

        # When the reviewed encounter-specific forum shape is extracted
        changes = extract_changes(document)

        # Then its bullets are retained as one raid record
        self.assertEqual(1, len(changes))
        self.assertEqual("Raid", changes[0].category)
        self.assertEqual("The Venomous Abyss", changes[0].name)
        self.assertEqual(date(2026, 8, 23), changes[0].effective_date)
        self.assertEqual(
            (
                "Abyssal Rain's initial damage reduced by 12.5% on Mythic "
                "difficulty",
                "Frost Burst damage reduced by 40%",
            ),
            changes[0].change,
        )

    def test_skips_unscoped_dungeon_prose_in_the_august_hotfix_shape(self) -> None:
        # Given Blizzard places a general sentence before a named dungeon
        document = _document(
            "live-hotfix-august-13-2026.html",
            channel="live",
        )

        # When the reviewed current article shape is extracted
        changes = extract_changes(document)

        # Then only the explicitly named dungeon change is published
        self.assertEqual(1, len(changes))
        self.assertEqual("Altar of Fangs", changes[0].name)
        self.assertEqual(
            ("Example encounter change.",),
            changes[0].change,
        )

    def test_extracts_the_tidebound_grotto_from_august_hotfixes(self) -> None:
        # Given Blizzard publishes the new dungeon in the combined section
        document = _document(
            "live-hotfix-august-25-2026.html",
            channel="live",
        )

        # When the reviewed current article shape is extracted
        changes = extract_changes(document)

        # Then the dungeon owns its complete ordered change list
        self.assertEqual(1, len(changes))
        self.assertEqual("Dungeon", changes[0].category)
        self.assertEqual("The Tidebound Grotto", changes[0].name)
        self.assertEqual(
            (
                "Health of Nymrissa Wavecaller reduced by 5% on Heroic "
                "difficulty and 10% on Mythic difficulty.",
                "Frost Burst damage reduced by 40%.",
            ),
            changes[0].change,
        )

    def test_extracts_the_reviewed_september_hotfix_shape(self) -> None:
        # Given Blizzard omits "The" and follows with new non-target sections
        document = _document(
            "live-hotfix-september-3-2026.html",
            channel="live",
        )

        # When the reviewed September article shape is extracted
        changes = extract_changes(document)

        # Then only the canonical dungeon record is published
        self.assertEqual(1, len(changes))
        self.assertEqual("Dungeon", changes[0].category)
        self.assertEqual("The Tidebound Grotto", changes[0].name)
        self.assertEqual(date(2026, 9, 1), changes[0].effective_date)
        self.assertEqual(
            (
                "Nymrissa Wavecaller and her murlocs’ health reduced by up "
                "to 10% for lower group sizes on Normal, Heroic, and Mythic "
                "difficulties.",
                "Frost Orb aura duration reduced to 12 seconds (was 16 "
                "seconds).",
            ),
            changes[0].change,
        )

    def test_canonicalizes_blizzards_venemous_abyss_typo(self) -> None:
        # Given Blizzard misspells the raid heading in the August 27 article
        document = _document(
            "live-hotfix-august-27-2026.html",
            channel="live",
        )

        # When the reviewed current article shape is extracted
        changes = extract_changes(document)

        # Then the typo resolves to the canonical raid name
        self.assertEqual(1, len(changes))
        self.assertEqual("Raid", changes[0].category)
        self.assertEqual("The Venomous Abyss", changes[0].name)
        self.assertEqual(
            (
                "Story Mode: Dungeon followers will now properly lead "
                "players when Dungeon Assistance is toggled on.",
            ),
            changes[0].change,
        )

    def test_extracts_a_registered_raid_embedded_in_combined_section_prose(
        self,
    ) -> None:
        # Given Blizzard names a raid inside a top-level combined-section bullet
        document = replace(
            _document("live-hotfix-notes.html", channel="live"),
            body=(
                b"<p><strong>August 14, 2026</strong></p>"
                b"<p><strong>Dungeons and Raids</strong></p>"
                b"<ul><li>Archmage Timear again permits players to queue for "
                b"the Raid Finder wings of Tomb of Sargeras.</li></ul>"
                b"<p><strong>Items</strong></p>"
                b"<ul><li>An unrelated item change.</li></ul>"
            ),
        )

        # When the reviewed current article shape is extracted
        changes = extract_changes(document)

        # Then the exact registered raid owns the unchanged source sentence
        self.assertEqual(1, len(changes))
        self.assertEqual("Raid", changes[0].category)
        self.assertEqual("Tomb of Sargeras", changes[0].name)
        self.assertEqual(
            (
                "Archmage Timear again permits players to queue for the Raid "
                "Finder wings of Tomb of Sargeras.",
            ),
            changes[0].change,
        )

    def test_maps_the_orphaned_ulatek_encounter_to_its_raid(self) -> None:
        # Given Blizzard omits the raid heading above the Ula'tek encounter
        document = _document(
            "live-hotfix-august-21-2026.html",
            channel="live",
        )

        # When the reviewed August 21 article shape is extracted
        changes = extract_changes(document)

        # Then both bullets remain unchanged under The Venomous Abyss
        self.assertEqual(1, len(changes))
        self.assertEqual("Raid", changes[0].category)
        self.assertEqual("The Venomous Abyss", changes[0].name)
        self.assertEqual(
            (
                "Ula’tek: Adjusted the Caustic Waves from the Gore Rattler "
                "so they remain above the floor of the main platform.",
                "Ula’tek: The tooltip for Ula'tek's Volatile Purge no "
                "longer contains an error.",
            ),
            changes[0].change,
        )

    def test_unsupported_sections_do_not_leak_into_a_class(self) -> None:
        # Given an unsupported section follows a named class
        document = replace(
            _document("live-hotfix-notes.html", channel="live"),
            body=(
                b"<p><strong>August 14, 2026</strong></p>"
                b"<p><strong>Classes</strong></p>"
                b"<ul><li><strong>Warlock</strong><ul>"
                b"<li>A class change.</li></ul></li></ul>"
                b"<p><strong>Delves</strong></p>"
                b"<ul><li>An unrelated Delve change.</li></ul>"
            ),
        )

        # When the reviewed section boundary is extracted
        changes = extract_changes(document)

        # Then the unsupported bullet is not assigned to Warlock
        self.assertEqual(1, len(changes))
        self.assertEqual("Warlock", changes[0].name)
        self.assertEqual(("A class change.",), changes[0].change)

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
