import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "scripts"
    / "apply_translation_fallbacks.py"
)


def _load_module():
    assert SCRIPT_PATH.exists(), "fallback application script is missing"
    spec = importlib.util.spec_from_file_location(
        "apply_translation_fallbacks",
        SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load fallback application script")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def _localization(name: str, text: str, translation_type: str) -> dict:
    return {
        "name": name,
        "specialization": "Balance",
        "source": "Blizzard",
        "sourceUrl": "https://worldofwarcraft.blizzard.com/",
        "translationType": translation_type,
        "translatedFrom": "" if translation_type == "official" else "en",
        "change": [text],
        "terminologySourceUrls": [],
    }


def _document() -> dict:
    return {
        "schemaVersion": 5,
        "updatedAt": "2026-08-02T19:00:00+02:00",
        "changes": [
            {
                "id": "change-druid-balance",
                "channel": "ptr",
                "category": "Class",
                "date": "2026-08-01",
                "patch": "12.1",
                "localizations": {
                    "en": _localization(
                        "Druid",
                        "Moonfire damage increased by 5%.",
                        "official",
                    ),
                    "deDE": _localization(
                        "Druide",
                        "Moonfire Schaden erhöht 5%.",
                        "agent",
                    ),
                    "frFR": _localization(
                        "Druide",
                        "Dégâts de Moonfire augmentés de 5%.",
                        "agent",
                    ),
                },
                "retrievedAt": "2026-08-02T19:00:00+02:00",
            }
        ],
    }


def _batch(document: dict) -> dict:
    return {
        **document,
        "localeCompletion": {
            "localized": ["frFR"],
            "fallbacks": {
                "deDE": "Verified terminology was unavailable.",
            },
        },
    }


# Describe: publishing audited English fallback classifications
class TranslationFallbackApplicationTests(unittest.TestCase):
    def test_removes_only_fallback_locales_and_regenerates_lua(self) -> None:
        # Given canonical data and a matching audited fallback batch
        module = _load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            data_path = directory / "retail-patch-notes.json"
            batch_path = directory / "translation-batch.json"
            lua_path = directory / "PatchNotesData.lua"
            document = _document()
            data_path.write_text(
                json.dumps(document),
                encoding="utf-8",
            )
            batch_path.write_text(
                json.dumps(_batch(document)),
                encoding="utf-8",
            )

            # When the fallback classifications are published
            result = module.apply_translation_fallbacks(
                data_path=data_path,
                batch_path=batch_path,
                lua_path=lua_path,
            )

            # Then only rejected German text is removed from JSON and Lua
            published = json.loads(data_path.read_text(encoding="utf-8"))
            localizations = published["changes"][0]["localizations"]
            self.assertEqual({"en", "frFR"}, set(localizations))
            self.assertEqual(1, result.removed_localizations)
            self.assertEqual(("deDE",), result.fallback_locales)

            lua_text = lua_path.read_text(encoding="utf-8")
            self.assertNotIn("Moonfire Schaden", lua_text)
            self.assertIn("Dégâts de Moonfire", lua_text)

    def test_rejects_a_stale_batch_without_changing_outputs(self) -> None:
        # Given a fallback batch prepared for another canonical snapshot
        module = _load_module()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            data_path = directory / "retail-patch-notes.json"
            batch_path = directory / "translation-batch.json"
            lua_path = directory / "PatchNotesData.lua"
            document = _document()
            stale_batch = _batch(document)
            stale_batch["updatedAt"] = "2026-08-01T19:00:00+02:00"
            original_json = json.dumps(document)
            original_lua = "existing lua"
            data_path.write_text(original_json, encoding="utf-8")
            batch_path.write_text(
                json.dumps(stale_batch),
                encoding="utf-8",
            )
            lua_path.write_text(original_lua, encoding="utf-8")

            # When fallback publication is attempted
            with self.assertRaisesRegex(ValueError, "snapshot"):
                module.apply_translation_fallbacks(
                    data_path=data_path,
                    batch_path=batch_path,
                    lua_path=lua_path,
                )

            # Then neither canonical output is changed
            self.assertEqual(
                original_json,
                data_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                original_lua,
                lua_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
