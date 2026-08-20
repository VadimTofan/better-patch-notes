from datetime import date, datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from automation.acquisition import english_acquisition_sources, prepare_acquisition
from automation.models import ExtractedChange


# Describe: artifact-only English acquisition
class AcquisitionTests(unittest.TestCase):
    def test_selects_only_version_and_english_sources(self) -> None:
        # Given a registry containing version, English, and localized sources
        sources = (
            SimpleNamespace(kind="version", locale="en"),
            SimpleNamespace(kind="news_feed", locale="en"),
            SimpleNamespace(kind="news_feed", locale="frFR"),
        )

        # When acquisition selects the sources it will fetch
        selected = english_acquisition_sources(sources)

        # Then localized sources are deferred to their locale jobs
        self.assertEqual(sources[:2], selected)

    def test_changed_english_data_is_written_without_editing_canonical_data(
        self,
    ) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given canonical data and one newly acquired English change
            root = Path(temporary_directory)
            data_path = root / "retail-patch-notes.json"
            lua_path = root / "PatchNotesData.lua"
            output_directory = root / "artifacts"
            canonical = {
                "schemaVersion": 5,
                "updatedAt": "2026-08-19T04:07:00+00:00",
                "changes": [],
            }
            data_path.write_text(json.dumps(canonical), encoding="utf-8")
            lua_path.write_text("return {}\n", encoding="utf-8")
            original_data = data_path.read_bytes()
            original_lua = lua_path.read_bytes()
            change = ExtractedChange(
                channel="live",
                category="Class",
                effective_date=date(2026, 8, 19),
                patch="12.1.0",
                name="Druid",
                specialization="Restoration",
                change=("Fixed Rejuvenation.",),
                source_url="https://news.blizzard.com/example",
            )

            def refresh(input_path, staged_data, staged_lua, _patch):
                document = json.loads(input_path.read_text(encoding="utf-8"))
                self.assertIn("retrievedAt", document)
                self.assertNotIn("updatedAt", document)
                self.assertEqual(
                    "",
                    document["changes"][0]["replacesSourceUrl"],
                )
                staged_data.write_text(
                    json.dumps(
                        {
                            "schemaVersion": 5,
                            "updatedAt": document["retrievedAt"],
                            "changes": document["changes"],
                        }
                    ),
                    encoding="utf-8",
                )
                staged_lua.write_text("return { changed = true }\n", encoding="utf-8")
                return SimpleNamespace(
                    added=1,
                    skipped=0,
                    promoted=0,
                    localized=0,
                    ambiguous=0,
                    removed=0,
                )

            # When acquisition prepares its immutable workflow artifacts
            outcome = prepare_acquisition(
                changes=(change,),
                current_patch="12.1.0",
                refreshed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                canonical_data_path=data_path,
                canonical_lua_path=lua_path,
                output_directory=output_directory,
                refresh=refresh,
            )

            # Then data is marked changed without editing either release file
            self.assertEqual("DATA_CHANGED", outcome.status)
            self.assertEqual(original_data, data_path.read_bytes())
            self.assertEqual(original_lua, lua_path.read_bytes())
            english = json.loads(
                (output_directory / "english-document.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual({"en"}, set(english["changes"][0]["localizations"]))
            result = json.loads(
                (output_directory / "acquisition-result.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("DATA_CHANGED", result["status"])
            self.assertEqual(1, result["accepted"])

    def test_timestamp_only_refresh_is_no_change(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a refresher that changes only the top-level timestamp
            root = Path(temporary_directory)
            data_path = root / "retail-patch-notes.json"
            lua_path = root / "PatchNotesData.lua"
            output_directory = root / "artifacts"
            canonical = {
                "schemaVersion": 5,
                "updatedAt": "2026-08-19T04:07:00+00:00",
                "changes": [],
            }
            data_path.write_text(json.dumps(canonical), encoding="utf-8")
            lua_path.write_text("return {}\n", encoding="utf-8")

            def refresh(_input_path, staged_data, _staged_lua, _patch):
                updated = dict(canonical)
                updated["updatedAt"] = "2026-08-20T04:07:00+00:00"
                staged_data.write_text(json.dumps(updated), encoding="utf-8")
                return SimpleNamespace(
                    added=0,
                    skipped=0,
                    promoted=0,
                    localized=0,
                    ambiguous=0,
                    removed=0,
                )

            # When acquisition compares the staged refresh
            outcome = prepare_acquisition(
                changes=(),
                current_patch="12.1.0",
                refreshed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                canonical_data_path=data_path,
                canonical_lua_path=lua_path,
                output_directory=output_directory,
                refresh=refresh,
            )

            # Then it stops before translation
            self.assertEqual("NO_CHANGE", outcome.status)


if __name__ == "__main__":
    unittest.main()
