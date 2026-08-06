from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


from automation.coordinator import (
    SUPPORTED_TRANSLATION_LOCALES,
    build_english_document,
    coordinate_release,
)
from automation.models import ExtractedChange, RefreshStatus
from automation.release_files import ReleaseFiles, read_versions


@dataclass(frozen=True)
class _TranslationReport:
    validated_locales: tuple[str, ...]
    fallback_locales: tuple[str, ...] = ()
    uncertain_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RefreshResult:
    added: int = 1
    skipped: int = 0
    promoted: int = 0
    localized: int = 10
    ambiguous: int = 0
    removed: int = 0


def _release_files(root: Path) -> ReleaseFiles:
    version = "0.2.9"
    (root / "BetterPatchNotes.toc").write_text(
        f"## Interface: 120007\n## Version: {version}\n",
        encoding="utf-8",
    )
    (root / "Addon.lua").write_text(
        f'addon.version = "{version}"\n',
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        f"- **Addon version:** {version}\n",
        encoding="utf-8",
    )
    (root / "changelog.txt").write_text(
        f"Version {version} - 2026-08-04\n- Previous\n",
        encoding="utf-8",
    )
    (root / "data.json").write_text(
        json.dumps(
            {
                "schemaVersion": 5,
                "updatedAt": "2026-08-04T04:07:00+02:00",
                "changes": [],
            }
        ),
        encoding="utf-8",
    )
    (root / "PatchNotesData.lua").write_text("old lua", encoding="utf-8")

    return ReleaseFiles(
        toc=root / "BetterPatchNotes.toc",
        addon=root / "Addon.lua",
        readme=root / "README.md",
        changelog=root / "changelog.txt",
        data=root / "data.json",
        lua=root / "PatchNotesData.lua",
    )


def _english_document() -> dict[str, object]:
    change = ExtractedChange(
        channel="ptr",
        category="Class",
        effective_date=date(2026, 8, 1),
        patch="12.1.0",
        name="Mage",
        specialization="Arcane",
        change=("Arcane Blast damage increased by 20%.",),
        source_url="https://us.forums.blizzard.com/en/wow/t/notes/1/18",
    )

    return build_english_document(
        (change,),
        "2026-08-05T04:07:00+02:00",
    )


def _translated_batch(document: dict[str, object]) -> dict[str, object]:
    batch = {
        "retrievedAt": document["updatedAt"],
        "changes": json.loads(json.dumps(document["changes"])),
    }
    for change in batch["changes"]:
        english = change["localizations"]["en"]
        for locale in SUPPORTED_TRANSLATION_LOCALES:
            change["localizations"][locale] = {
                **english,
                "translationType": "agent",
                "translatedFrom": "en",
                "terminologySourceUrls": [
                    f"https://worldofwarcraft.blizzard.com/{locale}/game/classes/druid"
                ],
            }

    return batch


def _validator(batch: dict[str, object]) -> _TranslationReport:
    return _TranslationReport(
        validated_locales=tuple(sorted(SUPPORTED_TRANSLATION_LOCALES))
    )


# Describe: all-or-nothing automatic refresh coordination
class AutomationCoordinatorTests(unittest.TestCase):
    def test_builds_schema_compatible_english_input(self) -> None:
        # Given / When
        document = _english_document()

        # Then
        change = document["changes"][0]
        english = change["localizations"]["en"]
        self.assertEqual(english["change"], ["Arcane Blast damage increased by 20%."])
        self.assertEqual(english["translationType"], "official")
        self.assertEqual(english["source"], "Blizzard")

    def test_no_change_restores_every_release_file_byte(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            files = _release_files(Path(temporary_directory))
            before = {path: path.read_bytes() for path in files.paths()}

            def refresh(batch_path: Path, data: Path, lua: Path, patch: str):
                current = json.loads(data.read_text(encoding="utf-8"))
                current["updatedAt"] = "2026-08-05T04:07:00+02:00"
                data.write_text(json.dumps(current), encoding="utf-8")
                lua.write_text("timestamp-only lua", encoding="utf-8")
                return _RefreshResult(added=0, localized=0)

            # When
            outcome = coordinate_release(
                files=files,
                english_document=_english_document(),
                current_patch="12.0.7",
                release_date=date(2026, 8, 5),
                translate=_translated_batch,
                validate=_validator,
                refresh=refresh,
            )

            # Then
            self.assertEqual(outcome.status, RefreshStatus.NO_CHANGE)
            self.assertEqual(
                {path: path.read_bytes() for path in files.paths()},
                before,
            )

    def test_one_failed_locale_blocks_and_restores_the_release(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            files = _release_files(Path(temporary_directory))
            before = {path: path.read_bytes() for path in files.paths()}

            def failed_validator(batch: dict[str, object]) -> _TranslationReport:
                return _TranslationReport(
                    validated_locales=tuple(
                        sorted(SUPPORTED_TRANSLATION_LOCALES - {"ruRU"})
                    ),
                    fallback_locales=("ruRU",),
                )

            # When
            outcome = coordinate_release(
                files=files,
                english_document=_english_document(),
                current_patch="12.0.7",
                release_date=date(2026, 8, 5),
                translate=_translated_batch,
                validate=failed_validator,
                refresh=lambda *args: _RefreshResult(),
            )

            # Then
            self.assertEqual(outcome.status, RefreshStatus.BLOCKED)
            self.assertIn("ruRU", outcome.reason)
            self.assertEqual(
                {path: path.read_bytes() for path in files.paths()},
                before,
            )

    def test_meaningful_change_prepares_one_synchronized_release(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            files = _release_files(Path(temporary_directory))

            def refresh(batch_path: Path, data: Path, lua: Path, patch: str):
                changed = {
                    "schemaVersion": 5,
                    "updatedAt": "2026-08-05T04:07:00+02:00",
                    "changes": [{"id": "new-change"}],
                }
                data.write_text(json.dumps(changed), encoding="utf-8")
                lua.write_text("new lua", encoding="utf-8")
                return _RefreshResult()

            # When
            outcome = coordinate_release(
                files=files,
                english_document=_english_document(),
                current_patch="12.0.7",
                release_date=date(2026, 8, 5),
                translate=_translated_batch,
                validate=_validator,
                refresh=refresh,
            )

            # Then
            self.assertEqual(outcome.status, RefreshStatus.RELEASE_READY)
            self.assertEqual(outcome.version, "0.2.10")
            self.assertEqual(read_versions(files), {"0.2.10"})

    def test_empty_collection_can_prune_stale_data_without_translation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            files = _release_files(Path(temporary_directory))
            english_document = build_english_document(
                (),
                "2026-08-05T04:07:00+02:00",
            )

            def must_not_run(*args):
                raise AssertionError("translation is unnecessary for empty input")

            def refresh(batch_path: Path, data: Path, lua: Path, patch: str):
                batch = json.loads(batch_path.read_text(encoding="utf-8"))
                self.assertEqual(batch["changes"], [])
                current = json.loads(data.read_text(encoding="utf-8"))
                current["changes"] = [{"id": "retained"}]
                data.write_text(json.dumps(current), encoding="utf-8")
                lua.write_text("pruned lua", encoding="utf-8")
                return _RefreshResult(added=0, localized=0, removed=1)

            # When
            outcome = coordinate_release(
                files=files,
                english_document=english_document,
                current_patch="12.0.7",
                release_date=date(2026, 8, 5),
                translate=must_not_run,
                validate=must_not_run,
                refresh=refresh,
            )

            # Then
            self.assertEqual(outcome.status, RefreshStatus.RELEASE_READY)
            self.assertEqual(outcome.removed, 1)


if __name__ == "__main__":
    unittest.main()
