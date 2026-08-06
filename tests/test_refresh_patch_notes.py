import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFRESH_PATH = (
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "scripts"
    / "refresh_patch_notes.py"
)


def _load_refresh_module():
    specification = importlib.util.spec_from_file_location(
        "refresh_patch_notes",
        REFRESH_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load refresh_patch_notes.py")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)

    return module


def _write_batch(
    path: Path,
    change_text: str = "Damage increased.",
    patch_version: str = "12.0.7",
) -> None:
    document = {
        "retrievedAt": "2026-08-01T12:00:00+02:00",
        "changes": [
            {
                "channel": "live",
                "category": "Class",
                "date": "2026-08-01",
                "patch": patch_version,
                "localizations": {
                    "en": {
                        "name": "Mage",
                        "specialization": "Arcane",
                        "change": [change_text],
                        "source": "Blizzard",
                        "sourceUrl": (
                            "https://worldofwarcraft.blizzard.com/example"
                        ),
                    }
                },
                "replacesSourceUrl": "",
            }
        ],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


def _run_refresh(
    input_path: Path,
    data_path: Path,
    lua_path: Path,
    game_version: str = "12.0.7",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REFRESH_PATH),
            "--input",
            str(input_path),
            "--data",
            str(data_path),
            "--lua-output",
            str(lua_path),
            "--game-version",
            game_version,
        ],
        capture_output=True,
        check=False,
        text=True,
    )


# Describe: one-command canonical JSON and runtime Lua publishing
class PatchNoteRefreshTests(unittest.TestCase):
    def test_canonical_data_matches_the_installed_retail_build(self) -> None:
        # Given the installed Retail build and canonical patch-note document
        module = _load_refresh_module()
        if not module.DEFAULT_BUILD_INFO_PATH.exists():
            self.skipTest("installed Retail .build.info is unavailable")
        game_patch = module.detect_game_patch(
            module.DEFAULT_BUILD_INFO_PATH
        )
        data_path = PROJECT_ROOT / "data" / "retail-patch-notes.json"
        document = json.loads(data_path.read_text(encoding="utf-8"))
        as_of_date = str(document["updatedAt"]).split("T", 1)[0]

        # When current-build retention is evaluated without publishing
        retained_document, removed = module.retain_relevant_changes(
            document,
            game_patch,
            as_of_date,
        )

        # Then every stored record is relevant to this WoW installation
        self.assertEqual(0, removed)
        self.assertEqual(document["changes"], retained_document["changes"])

    def test_detects_the_active_retail_patch_from_build_info(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given Blizzard build metadata with active Retail and Classic rows
            build_info_path = Path(temporary_directory) / ".build.info"
            build_info_path.write_text(
                "Active!DEC:1|Version!STRING:0|Product!STRING:0\n"
                "0|2.5.6.68941|wow_anniversary\n"
                "1|12.0.7.68887|wow\n",
                encoding="utf-8",
            )
            module = _load_refresh_module()

            # When the installed Retail patch is detected
            game_patch = module.detect_game_patch(build_info_path)

            # Then the build component is removed from the patch version
            self.assertEqual("12.0.7", game_patch)

    def test_keeps_exact_live_and_future_ptr_patch_records_only(self) -> None:
        # Given records before, at, and after the current game patch
        module = _load_refresh_module()
        document = {
            "schemaVersion": 2,
            "updatedAt": "2026-08-01T12:00:00+02:00",
            "changes": [
                {
                    "id": "live-current",
                    "channel": "live",
                    "patch": "12.0.7",
                    "date": "2026-08-02",
                },
                {
                    "id": "live-old",
                    "channel": "live",
                    "patch": "12.0.6",
                    "date": "2026-08-02",
                },
                {
                    "id": "ptr-future",
                    "channel": "ptr",
                    "patch": "12.1",
                    "date": "2026-08-02",
                },
                {
                    "id": "ptr-current",
                    "channel": "ptr",
                    "patch": "12.0.7",
                    "date": "2026-08-02",
                },
                {
                    "id": "ptr-old",
                    "channel": "ptr",
                    "patch": "11.2.7",
                    "date": "2026-08-02",
                },
                {
                    "id": "live-blank",
                    "channel": "live",
                    "patch": "",
                    "date": "2026-08-02",
                },
            ],
        }

        # When retention is applied for the installed build
        retained_document, removed = module.retain_relevant_changes(
            document,
            "12.0.7",
            "2026-08-02",
        )

        # Then only exact Live and newer PTR records remain
        self.assertEqual(4, removed)
        self.assertEqual(
            ["live-current", "ptr-future"],
            [change["id"] for change in retained_document["changes"]],
        )

    def test_removes_changes_older_than_the_rolling_fourteen_days(self) -> None:
        # Given changes on, before, and after the inclusive cutoff date
        module = _load_refresh_module()
        document = {
            "schemaVersion": 3,
            "updatedAt": "2026-08-02T12:00:00+02:00",
            "changes": [
                {
                    "id": "cutoff",
                    "channel": "live",
                    "patch": "12.0.7",
                    "date": "2026-07-20",
                },
                {
                    "id": "too-old",
                    "channel": "live",
                    "patch": "12.0.7",
                    "date": "2026-07-19",
                },
                {
                    "id": "recent-ptr",
                    "channel": "ptr",
                    "patch": "12.1",
                    "date": "2026-08-02",
                },
            ],
        }

        # When build and rolling-date retention are applied together
        retained_document, removed = module.retain_relevant_changes(
            document,
            "12.0.7",
            "2026-08-02",
        )

        # Then the cutoff is included and the preceding day is removed
        self.assertEqual(1, removed)
        self.assertEqual(
            ["cutoff", "recent-ptr"],
            [change["id"] for change in retained_document["changes"]],
        )

    def test_refresh_removes_records_from_the_previous_live_build(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given patch notes published for the previous installed build
            temporary_path = Path(temporary_directory)
            previous_path = temporary_path / "previous.json"
            current_path = temporary_path / "current.json"
            data_path = temporary_path / "retail-patch-notes.json"
            lua_path = temporary_path / "PatchNotesData.lua"
            _write_batch(
                previous_path,
                "Previous-build change.",
                "12.0.6",
            )
            previous_result = _run_refresh(
                previous_path,
                data_path,
                lua_path,
                "12.0.6",
            )
            self.assertEqual(
                0,
                previous_result.returncode,
                previous_result.stderr,
            )
            _write_batch(
                current_path,
                "Current-build change.",
                "12.0.7",
            )

            # When the data is refreshed for the upgraded client
            result = _run_refresh(
                current_path,
                data_path,
                lua_path,
                "12.0.7",
            )

            # Then stale Live notes leave both synchronized outputs
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["removed"])
            document = json.loads(data_path.read_text(encoding="utf-8"))
            self.assertEqual(
                ["12.0.7"],
                [change["patch"] for change in document["changes"]],
            )
            lua_text = lua_path.read_text(encoding="utf-8")
            self.assertIn("Current-build change.", lua_text)
            self.assertNotIn("Previous-build change.", lua_text)

    def test_publishes_matching_json_and_lua_outputs(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a valid official patch-note batch
            temporary_path = Path(temporary_directory)
            input_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            lua_path = temporary_path / "PatchNotesData.lua"
            _write_batch(input_path)

            # When the one-command refresh is run
            result = _run_refresh(input_path, data_path, lua_path)

            # Then both canonical JSON and loadable Lua contain the change
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(data_path.exists())
            self.assertTrue(lua_path.exists())
            self.assertIn("Damage increased.", data_path.read_text("utf-8"))
            lua_text = lua_path.read_text("utf-8")
            self.assertIn("Damage increased.", lua_text)
            self.assertIn('classToken = "MAGE"', lua_text)

    def test_invalid_input_preserves_both_existing_outputs(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given published outputs and an invalid incoming batch
            temporary_path = Path(temporary_directory)
            input_path = temporary_path / "invalid.json"
            data_path = temporary_path / "retail-patch-notes.json"
            lua_path = temporary_path / "PatchNotesData.lua"
            input_path.write_text("not json", encoding="utf-8")
            data_path.write_text("old json", encoding="utf-8")
            lua_path.write_text("old lua", encoding="utf-8")

            # When refresh validation fails
            result = _run_refresh(input_path, data_path, lua_path)

            # Then neither published file changes
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("old json", data_path.read_text("utf-8"))
            self.assertEqual("old lua", lua_path.read_text("utf-8"))

    def test_generation_failure_preserves_both_existing_outputs(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given valid input, published outputs, and a failed Lua render
            temporary_path = Path(temporary_directory)
            initial_path = temporary_path / "initial.json"
            input_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            lua_path = temporary_path / "PatchNotesData.lua"
            _write_batch(initial_path, "Original change.")
            initial_result = _run_refresh(initial_path, data_path, lua_path)
            self.assertEqual(
                0,
                initial_result.returncode,
                initial_result.stderr,
            )
            original_json = data_path.read_text("utf-8")
            original_lua = lua_path.read_text("utf-8")
            _write_batch(input_path, "Replacement change.")
            module = _load_refresh_module()

            # When Lua generation fails before publishing
            with patch.object(
                module,
                "render_lua_data",
                side_effect=ValueError("render failed"),
            ):
                with self.assertRaisesRegex(ValueError, "render failed"):
                    module.refresh_patch_notes(
                        input_path,
                        data_path,
                        lua_path,
                        game_version="12.0.7",
                    )

            # Then neither published file changes
            self.assertEqual(original_json, data_path.read_text("utf-8"))
            self.assertEqual(original_lua, lua_path.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
