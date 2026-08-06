from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = (
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "SKILL.md"
)
JSON_DATA_PATH = PROJECT_ROOT / "data" / "retail-patch-notes.json"
AGENTS_PATH = PROJECT_ROOT / "AGENTS.md"
CHANGELOG_PATH = PROJECT_ROOT / "changelog.txt"
LEGACY_PATHS = (
    PROJECT_ROOT / "data" / "retail-patch-notes.xlsx",
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "scripts"
    / "update_workbook.py",
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "scripts"
    / "requirements.txt",
    PROJECT_ROOT / "tests" / "test_update_workbook.py",
)


# Describe: repository-local Retail patch-note research skill
class SkillContractTests(unittest.TestCase):
    def test_skill_defines_the_approved_research_contract(self) -> None:
        # Given an approved contract for the research skill
        required_phrases = (
            "name: fetch-retail-patch-notes",
            "Blizzard > Wowhead = MMO-Champion > other credible sources",
            "live Retail",
            "data/retail-patch-notes.json",
            "schemaVersion",
            '"channel": "live"',
            '"channel": "ptr"',
            '"localizations"',
            '"change": [',
            '"en"',
            "enUS and enGB clients map to `en`",
            "official Blizzard translations",
            "skills/translate-patch-notes/SKILL.md",
            "agent translations",
            "localization-first",
            "English is the fallback language",
            "official localization",
            "validated unofficial translation",
            "documented fallback reason",
            "must not complete the refresh",
            "locale | official | agent translation | English fallback | reason",
            "uncertain terminology",
            "English fallback",
            "refresh_patch_notes.py",
            "--lua-output PatchNotesData.lua",
            "automatically generates",
            "current installed Retail patch",
            "must match the current patch exactly",
            "must be newer than the current patch",
            ".build.info",
            "--game-version",
            "removed",
            "14-day rolling retention",
            "direct source URL",
            "untrusted content",
            "future database",
            "Updated: 2026-08-02",
            "Last reviewed: 2026-08-02",
        )
        forbidden_phrases = (
            "openpyxl",
            "spreadsheet",
            "update_workbook.py",
            ".xlsx",
            "Stop at canonical JSON",
            "Leave `patch` empty",
        )

        # When the repository-local skill is read
        self.assertTrue(
            SKILL_PATH.exists(),
            f"Repository-local skill is missing: {SKILL_PATH}",
        )
        skill_text = SKILL_PATH.read_text(encoding="utf-8")
        normalized_skill_text = " ".join(skill_text.split())

        # Then it contains every required policy and maintenance marker
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, normalized_skill_text)

        for phrase in forbidden_phrases:
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, skill_text.casefold())

    def test_skill_reports_an_explicit_audited_empty_result(self) -> None:
        # Given a completed search with no qualifying patch-note changes
        required_empty_result_phrases = (
            "No qualifying Retail class, dungeon, or raid patch-note updates "
            "were found.",
            "searched date range",
            "Live and PTR channels",
            "sources checked",
            "locale fallbacks",
        )

        # When the repository-local skill is read
        skill_text = " ".join(SKILL_PATH.read_text(encoding="utf-8").split())

        # Then it requires a clear result plus enough detail to audit the search
        for phrase in required_empty_result_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill_text)

    def test_json_storage_replaces_legacy_spreadsheet_files(self) -> None:
        # Given the approved JSON-only repository structure
        expected_json_path = JSON_DATA_PATH

        # When storage artifacts are inspected
        json_exists = expected_json_path.exists()
        existing_legacy_paths = [
            path for path in LEGACY_PATHS if path.exists()
        ]

        # Then canonical JSON exists and spreadsheet artifacts are absent
        self.assertTrue(
            json_exists,
            f"Canonical JSON data is missing: {expected_json_path}",
        )
        self.assertEqual([], existing_legacy_paths)

        data_text = expected_json_path.read_text(encoding="utf-8")
        self.assertIn('"schemaVersion": 5', data_text)
        self.assertIn('"channel": "live"', data_text)
        self.assertIn('"localizations"', data_text)
        self.assertIn('"en"', data_text)
        self.assertNotIn('"enUS"', data_text)
        self.assertNotIn('"enGB"', data_text)


# Describe: project-local patch-note release guidance
class ProjectGuidanceTests(unittest.TestCase):
    def test_guidance_defines_the_unattended_refresh_safety_contract(self) -> None:
        # Given
        required_phrases = (
            "Automatic Blizzard-Only Refresh",
            "04:07 Europe/Copenhagen",
            "Blizzard-only",
            "all locales must pass",
            "no meaningful packaged-data change",
            "must not use a personal access token",
            "Exact automated commit allowlist",
            "data/retail-patch-notes.json",
            "PatchNotesData.lua",
            "must not create a second version bump",
            "manual parser review",
        )

        # When
        guidance = " ".join(AGENTS_PATH.read_text(encoding="utf-8").split())

        # Then
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_guidance_separates_web_deploys_from_addon_releases(self) -> None:
        # Given one repository with Netlify and CurseForge deployment targets
        required_phrases = (
            "Public Website Policy",
            "web-app/",
            "data/retail-patch-notes.json",
            "Netlify",
            "web-only push",
            "must not trigger the CurseForge release workflow",
            "does not require an addon version bump",
        )

        # When durable project guidance is inspected
        guidance = " ".join(
            AGENTS_PATH.read_text(encoding="utf-8").split()
        )

        # Then deployment ownership remains explicit after context loss
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_guidance_defines_the_complete_language_and_locale_policy(
        self,
    ) -> None:
        # Given the durable language rules needed after conversation loss
        required_phrases = (
            "Language and Locale Policy",
            "`deDE`, `en`, `esES`, `esMX`, `frFR`, `itIT`, `koKR`, "
            "`ptBR`, `ruRU`, `zhCN`, and `zhTW`",
            "enUS and enGB clients map to `en`",
            "never store separate `enUS` or `enGB` localizations",
            "`esES` and `esMX` remain separate",
            "`zhCN` and `zhTW` remain separate",
            "automatic character conversion",
            "exact client locale",
            "interface localization does not prove",
            "official Blizzard localization",
            "validated unofficial translation",
            "documented English fallback",
            "official localized game terminology",
            "`translationType`",
            "`translatedFrom`",
            "`terminologySourceUrls`",
            "must not complete a refresh",
            "must not claim that every language has patch-note content",
            "`data/retail-patch-notes.json`",
        )

        # When the project-local agent guidance is read
        guidance = " ".join(
            AGENTS_PATH.read_text(encoding="utf-8").split()
        )

        # Then storage, runtime, translation, and reporting rules are explicit
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_guidance_requires_a_version_bump_before_every_github_push(
        self,
    ) -> None:
        # Given GitHub pushes automatically deploy releases to CurseForge
        required_phrases = (
            "GitHub Push Release Rule",
            "Every push to GitHub",
            "automatically deploys to CurseForge",
            "increment the semantic version's patch component",
            "origin/main",
            "Refuse to push",
            "BetterPatchNotes.toc",
            "Addon.lua",
            "README.md",
            "changelog.txt",
        )

        # When the project-local agent guidance is read
        guidance = " ".join(
            AGENTS_PATH.read_text(encoding="utf-8").split()
        )

        # Then every deployment push requires a synchronized new version
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_guidance_requires_the_complete_data_release_workflow(self) -> None:
        # Given the approved workflow for every patch-note refresh request
        required_phrases = (
            "Patch-Note Refresh Release Workflow",
            "skills/fetch-retail-patch-notes/SKILL.md",
            "skills/translate-patch-notes/SKILL.md",
            "data/retail-patch-notes.json",
            "PatchNotesData.lua",
            "MinimapButton.lua",
            "BetterPatchNotes.toc",
            "Addon.lua",
            "changelog.txt",
            "newest-first",
            "patch component",
            "packaged data actually changed",
            "rolling 14-day window",
            "non-empty array of strings",
            "internal provenance",
            "unofficial translation",
            "English fallbacks",
            "localization-first",
            "English is the fallback language",
            "official localization",
            "validated unofficial translation",
            "documented fallback reason",
            "must not complete the refresh",
            "locale | official | agent translation | English fallback | reason",
            "uncertain terminology",
            "must not appear in the addon UI",
            "Do not bump the version",
            "python -m unittest discover -s tests -v",
            "runtime release files only",
            "Do not include development files",
            "git add",
            "git commit",
            "git push origin main",
            "GitHub Actions",
            "CurseForge file ID",
            "release tag",
            "Do not create a manual release archive",
        )

        # When the project-local agent guidance is read
        self.assertTrue(AGENTS_PATH.exists())
        guidance = " ".join(
            AGENTS_PATH.read_text(encoding="utf-8").split()
        )

        # Then every mandatory refresh and release gate is explicit
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)
        self.assertTrue(CHANGELOG_PATH.exists())

    def test_exact_refresh_commands_authorize_a_complete_release(self) -> None:
        # Given two exact commands for a one-step data refresh and release
        required_phrases = (
            "Exact Refresh Command Authorization",
            "standalone command `refresh`",
            "standalone command `refresh data`",
            "explicit authorization for `git add`, `git commit`, and "
            "`git push origin main`",
            "read-only",
            "stop the entire operation",
            "timestamp-only",
            "Do not bump the version",
            "Do not modify `changelog.txt`",
            "Do not stage, commit, or push",
            "leave the working tree clean",
        )

        # When the project-local agent guidance is read
        guidance = " ".join(
            AGENTS_PATH.read_text(encoding="utf-8").split()
        )

        # Then exact refresh commands have narrow Git authorization and a
        # no-change refresh cannot create an empty release
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_guidance_preserves_class_browser_seen_state(self) -> None:
        # Given the approved class-browser behavior
        required_phrases = (
            "all 13 class icons",
            "localized class name",
            "all specialization-specific and class-wide changes together",
            "preserve the selected class",
            "reset to the player's actual class",
            "must not mark the browsed class as seen",
            "player's actual class",
        )

        # When the project-local agent guidance is read
        guidance = " ".join(
            AGENTS_PATH.read_text(encoding="utf-8").split()
        )

        # Then the transient browsing and seen-state invariants are explicit
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, guidance)

    def test_addon_versions_are_synchronized(self) -> None:
        # Given version declarations in every release-facing file
        toc_text = (PROJECT_ROOT / "BetterPatchNotes.toc").read_text(
            encoding="utf-8-sig"
        )
        addon_text = (PROJECT_ROOT / "Addon.lua").read_text(
            encoding="utf-8-sig"
        )
        readme_text = (PROJECT_ROOT / "README.md").read_text(
            encoding="utf-8-sig"
        )
        changelog_text = CHANGELOG_PATH.read_text(encoding="utf-8-sig")

        # When every semantic version is extracted
        toc_match = re.search(r"^## Version: (\d+\.\d+\.\d+)$", toc_text, re.M)
        addon_match = re.search(
            r'^addon\.version = "(\d+\.\d+\.\d+)"$',
            addon_text,
            re.M,
        )
        readme_match = re.search(
            r"^- \*\*Addon version:\*\* (\d+\.\d+\.\d+)$",
            readme_text,
            re.M,
        )
        changelog_match = re.search(
            r"^Version (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}$",
            changelog_text,
            re.M,
        )

        # Then every release surface exposes the same newest version
        self.assertIsNotNone(toc_match)
        self.assertIsNotNone(addon_match)
        self.assertIsNotNone(readme_match)
        self.assertIsNotNone(changelog_match)
        self.assertEqual(
            {
                toc_match.group(1),
                addon_match.group(1),
                readme_match.group(1),
                changelog_match.group(1),
            },
            {toc_match.group(1)},
        )


if __name__ == "__main__":
    unittest.main()
