from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


from automation.release_files import (
    ReleaseFiles,
    ReleaseSummary,
    has_meaningful_change,
    read_versions,
    restore_snapshot,
    snapshot_files,
    update_release_files,
)


def _canonical_data(updated_at: str, change: str = "Damage increased.") -> dict:
    return {
        "schemaVersion": 5,
        "updatedAt": updated_at,
        "changes": [{"id": "change-1", "change": [change]}],
    }


def _write_release_files(root: Path, version: str = "0.2.9") -> ReleaseFiles:
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
        f"Version {version} - 2026-08-04\n- Previous release\n",
        encoding="utf-8",
    )
    (root / "data.json").write_text("old json", encoding="utf-8")
    (root / "PatchNotesData.lua").write_text("old lua", encoding="utf-8")

    return ReleaseFiles(
        toc=root / "BetterPatchNotes.toc",
        addon=root / "Addon.lua",
        readme=root / "README.md",
        changelog=root / "changelog.txt",
        data=root / "data.json",
        lua=root / "PatchNotesData.lua",
    )


# Describe: byte-safe no-change and synchronized release preparation
class ReleaseFileTests(unittest.TestCase):
    def test_updated_at_alone_is_not_a_meaningful_change(self) -> None:
        # Given
        before = _canonical_data("2026-08-04T04:07:00+02:00")
        after = _canonical_data("2026-08-05T04:07:00+02:00")

        # When
        changed = has_meaningful_change(before, after)

        # Then
        self.assertFalse(changed)

    def test_record_content_is_a_meaningful_change(self) -> None:
        # Given
        before = _canonical_data("2026-08-04T04:07:00+02:00")
        after = _canonical_data(
            "2026-08-05T04:07:00+02:00",
            "Damage reduced.",
        )

        # When / Then
        self.assertTrue(has_meaningful_change(before, after))

    def test_bumps_and_synchronizes_the_patch_version_once(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            files = _write_release_files(Path(temporary_directory))
            summary = ReleaseSummary(
                live_patch="12.0.7",
                ptr_patch="12.1.0",
                added=2,
                updated=1,
                removed=0,
                locale_text="All ten translated locales validated",
            )

            # When
            version = update_release_files(
                files,
                date(2026, 8, 5),
                summary,
            )

            # Then
            self.assertEqual(version, "0.2.10")
            self.assertEqual(read_versions(files), {"0.2.10"})
            changelog = files.changelog.read_text(encoding="utf-8")
            self.assertTrue(changelog.startswith("Version 0.2.10 - 2026-08-05"))
            self.assertIn("- Data: Live 12.0.7; PTR 12.1.0", changelog)
            self.assertIn("- Removed: None", changelog)

    def test_snapshot_restores_exact_bytes(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            files = _write_release_files(Path(temporary_directory))
            snapshot = snapshot_files(files)
            files.data.write_text(
                json.dumps(_canonical_data("changed")),
                encoding="utf-8",
            )
            files.lua.write_bytes(b"changed lua\r\n")

            # When
            restore_snapshot(snapshot)

            # Then
            self.assertEqual(files.data.read_bytes(), b"old json")
            self.assertEqual(files.lua.read_bytes(), b"old lua")


if __name__ == "__main__":
    unittest.main()
