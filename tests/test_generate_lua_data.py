import importlib.util
import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = (
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "scripts"
    / "generate_lua_data.py"
)


def _load_generator():
    specification = importlib.util.spec_from_file_location(
        "generate_lua_data",
        GENERATOR_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("could not load Lua data generator")

    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    return module


def _document(**localization_overrides: object) -> dict[str, object]:
    localization = {
        "name": "Mage",
        "specialization": "Arcane",
        "change": ["Arcane Blast damage increased by 20%."],
        "source": "Blizzard",
        "sourceUrl": "https://example.com/notes",
        "translationType": "official",
        "translatedFrom": "",
        "terminologySourceUrls": [],
    }
    localization.update(localization_overrides)

    return {
        "schemaVersion": 5,
        "updatedAt": "2026-08-01T19:00:00+02:00",
        "changes": [
            {
                "id": "change-0123456789abcdef",
                "channel": "ptr",
                "category": "Class",
                "date": "2026-07-31",
                "patch": "12.1",
                "localizations": {"en": localization},
                "retrievedAt": "2026-08-01T19:00:00+02:00",
            }
        ],
    }


# Describe: deterministic WoW Lua data generation
class LuaDataGenerationTests(unittest.TestCase):
    def test_packaged_lua_matches_the_canonical_json_exactly(self) -> None:
        # Given the repository's canonical JSON and packaged Lua artifact
        generator = _load_generator()
        data_path = PROJECT_ROOT / "data" / "retail-patch-notes.json"
        lua_path = PROJECT_ROOT / "PatchNotesData.lua"
        document = json.loads(data_path.read_text(encoding="utf-8"))

        # When canonical JSON is rendered without writing either file
        expected_lua = generator.render_lua_data(document)

        # Then the Lua loaded by WoW is byte-for-byte current
        self.assertEqual(
            expected_lua,
            lua_path.read_text(encoding="utf-8"),
        )

    def test_generates_channel_versions_and_runtime_class_keys(self) -> None:
        # Given one canonical PTR Mage change
        generator = _load_generator()
        document = _document()

        # When the same document is rendered twice
        first_output = generator.render_lua_data(document)
        second_output = generator.render_lua_data(document)

        # Then output is stable and contains WoW runtime identifiers
        self.assertEqual(first_output, second_output)
        self.assertIn("addon.PatchNotesData =", first_output)
        self.assertIn("channelVersions", first_output)
        self.assertIn("classChannelVersions", first_output)
        self.assertIn('classToken = "MAGE"', first_output)
        self.assertIn("specializationId = 62", first_output)
        self.assertIn("recordCounts", first_output)
        self.assertIn('translationType = "official"', first_output)
        self.assertIn("ptr = 1", first_output)
        self.assertIn("latestDates", first_output)
        self.assertIn('ptr = "2026-07-31"', first_output)
        self.assertTrue(first_output.endswith("\n"))

    def test_versions_only_alert_classes_affected_by_the_changes(self) -> None:
        # Given a Mage-only change and a dungeon change shared by every class
        generator = _load_generator()
        mage_document = _document()
        dungeon_document = _document(
            name="The Dawnbreaker",
            specialization="",
        )
        dungeon_change = dungeon_document["changes"][0]
        dungeon_change["category"] = "Dungeon"

        # When per-class channel versions are prepared
        mage_versions = generator._prepare_document(
            mage_document
        )["classChannelVersions"]
        dungeon_versions = generator._prepare_document(
            dungeon_document
        )["classChannelVersions"]

        # Then Mage-only notes differ by class, while dungeon notes affect all
        self.assertNotEqual(
            mage_versions["MAGE"]["ptr"],
            mage_versions["WARRIOR"]["ptr"],
        )
        self.assertEqual(
            dungeon_versions["MAGE"]["ptr"],
            dungeon_versions["WARRIOR"]["ptr"],
        )

    def test_escapes_lua_strings_without_losing_unicode(self) -> None:
        # Given patch-note text containing Lua-sensitive characters
        generator = _load_generator()
        document = _document(
            change=['Quoted "spell" uses \\ path.\nÉlan increased.'],
        )

        # When the document is rendered
        output = generator.render_lua_data(document)

        # Then quotes, slashes, and newlines are escaped but Unicode remains
        self.assertIn(r'Quoted \"spell\" uses \\ path.\nÉlan increased.', output)
        self.assertNotIn('uses \\ path.\nÉlan', output)

    def test_rejects_an_unknown_class_before_rendering(self) -> None:
        # Given a canonical class record the addon cannot identify in game
        generator = _load_generator()
        document = _document(name="Tinker")

        # When rendering is attempted, then generation fails explicitly
        with self.assertRaisesRegex(ValueError, "unknown class"):
            generator.render_lua_data(document)

    def test_rejects_an_unknown_specialization_before_rendering(self) -> None:
        # Given a known class with an unknown specialization
        generator = _load_generator()
        document = _document(specialization="Chronomancer")

        # When rendering is attempted, then generation fails explicitly
        with self.assertRaisesRegex(ValueError, "unknown specialization"):
            generator.render_lua_data(document)


if __name__ == "__main__":
    unittest.main()
