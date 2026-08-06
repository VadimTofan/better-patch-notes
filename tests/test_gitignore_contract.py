from pathlib import Path
import subprocess
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAFE_DIRECTORY = str(PROJECT_ROOT).replace("\\", "/")


def _is_ignored(path: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={SAFE_DIRECTORY}",
            "check-ignore",
            "--quiet",
            "--no-index",
            path,
        ],
        cwd=PROJECT_ROOT,
        check=False,
    )

    return result.returncode == 0


# Describe: addon, website, and automatic refresh repository allowlist
class GitIgnoreContractTests(unittest.TestCase):
    def test_runtime_and_automation_inputs_are_trackable(self) -> None:
        # Given runtime files and the inputs required by scheduled refresh CI
        trackable_paths = (
            ".gitignore",
            ".github/workflows/release.yml",
            ".github/workflows/scheduled-refresh.yml",
            ".codex/config.toml",
            "AGENTS.md",
            "README.md",
            "LICENSE",
            "requirements-dev.txt",
            "BetterPatchNotes.toc",
            "Addon.lua",
            "Localization.lua",
            "PatchNotesData.lua",
            "Data.lua",
            "State.lua",
            "Window.lua",
            "MinimapButton.lua",
            "Core.lua",
            "changelog.txt",
            "data/retail-patch-notes.json",
            "automation/models.py",
            "automation/sources.json",
            "docs/automatic-refresh-operations.md",
            "skills/fetch-retail-patch-notes/scripts/refresh_patch_notes.py",
            "skills/translate-patch-notes/references/terminology.json",
            "skills/translate-patch-notes/scripts/generate_translations.py",
            "tests/test_automation_source_registry.py",
            "web-app/package.json",
            "web-app/src/main.ts",
            "netlify.toml",
        )

        # When Git evaluates the runtime-only allowlist
        ignored_paths = [
            path for path in trackable_paths if _is_ignored(path)
        ]

        # Then every approved repository file remains trackable
        self.assertEqual([], ignored_paths)

    def test_secrets_generated_files_and_unrelated_notes_stay_local(self) -> None:
        # Given secrets, generated artifacts, and unrelated local notes
        local_only_paths = (
            ".env",
            ".pkgmeta",
            "tests/__pycache__/test_addon_contract.cpython-311.pyc",
            "web-app/node_modules/vue/package.json",
            "web-app/dist/index.html",
            "web-app/.netlify/state.json",
            "web-app/src/generated/patch-notes.json",
            ".release/BetterPatchNotes-v0.2.1.zip",
            "BetterPatchNotes-v0.2.1.zip",
            "notes.txt",
        )

        # When Git evaluates the runtime-only allowlist
        visible_paths = [
            path for path in local_only_paths if not _is_ignored(path)
        ]

        # Then none of those paths can be added accidentally
        self.assertEqual([], visible_paths)


if __name__ == "__main__":
    unittest.main()
