import json
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = PROJECT_ROOT / "skills" / "translate-patch-notes"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
TERMINOLOGY_PATH = SKILL_ROOT / "references" / "terminology.json"
PROJECT_CONFIG_PATH = PROJECT_ROOT / ".codex" / "config.toml"
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements-dev.txt"
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"

SUPPORTED_TRANSLATION_LOCALES = {
    "deDE",
    "esES",
    "esMX",
    "frFR",
    "itIT",
    "koKR",
    "ptBR",
    "ruRU",
    "zhCN",
    "zhTW",
}


# Describe: grounded patch-note translation skill contract
class TranslationSkillContractTests(unittest.TestCase):
    def test_project_config_registers_the_translation_mcp_server(self) -> None:
        # Given an agent-assisted translation workflow for this repository
        expected_config = (
            "[mcp_servers.better_patch_notes_translation]",
            'command = "python"',
            'args = ["skills/translate-patch-notes/mcp_server/server.py"]',
            'default_tools_approval_mode = "writes"',
        )

        # When the project-scoped Codex configuration is inspected
        config = PROJECT_CONFIG_PATH.read_text(encoding="utf-8")

        # Then the local STDIO server is registered with write approvals
        for value in expected_config:
            with self.subTest(value=value):
                self.assertIn(value, config)

    def test_mcp_dependency_and_workspace_ignore_rules_are_declared(self) -> None:
        # Given a local MCP server with resumable untracked workspace state
        expected_dependency = "mcp>=1.27,<2"

        # When development dependencies and ignore rules are inspected
        requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
        gitignore = GITIGNORE_PATH.read_text(encoding="utf-8")

        # Then the stable SDK is pinned and generated work remains untracked
        self.assertIn(expected_dependency, requirements)
        self.assertIn("/.bpn-work/", gitignore)

    def test_skill_requires_grounded_unofficial_translations(self) -> None:
        # Given the approved translation trust and fallback policy
        required_phrases = (
            "name: translate-patch-notes",
            "official Blizzard localization",
            "unofficial translation",
            "translated from `en`",
            "enUS and enGB clients map to `en`",
            "English fallback",
            "localization-first",
            "English is the fallback language",
            "official localization",
            "validated unofficial translation",
            "documented fallback reason",
            "must not complete the refresh",
            "locale | official | agent translation | English fallback | reason",
            "Do not guess",
            "terminology.json",
            "validate_translations.py",
            "numbers, percentages, durations",
            "uncertain terminology",
            "agent-assisted refresh",
            "prepare_locale",
            "record_terminology",
            "submit_locale",
            "audit_locale",
            "compare_locale",
            "translation_status",
            "finalize_translations",
            "whole bullet",
            "separate review pass",
            "30-check audit",
            ".bpn-work/translation-batch.json",
            "must not modify canonical data",
            "apply_translation_fallbacks.py",
            "removes only locales classified as English fallbacks",
            "GEMINI_API_KEY",
            "GEMINI_API_KEY2",
            "do not write partial output",
            "Never fall back to an unauthenticated translation endpoint",
            "Gemini 3.5 Flash-Lite",
            "10 translation request starts per rolling minute",
            "authorization key",
            "September 2026",
            "Updated: 2026-08-06",
            "Last reviewed: 2026-08-05",
        )

        # When the repository-local translation skill is inspected
        skill_text = " ".join(SKILL_PATH.read_text(encoding="utf-8").split())

        # Then every source, labeling, validation, and maintenance rule exists
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, skill_text)

    def test_terminology_registry_covers_every_target_locale(self) -> None:
        # Given the ten non-English locales supported by the addon
        expected_locales = SUPPORTED_TRANSLATION_LOCALES

        # When the sourced terminology registry is loaded
        document = json.loads(TERMINOLOGY_PATH.read_text(encoding="utf-8"))
        actual_locales = set(document["locales"])

        # Then the registry is versioned and provides a bucket for every locale
        self.assertEqual(1, document["schemaVersion"])
        self.assertEqual(expected_locales, actual_locales)
        for locale, locale_data in document["locales"].items():
            with self.subTest(locale=locale):
                self.assertGreater(len(locale_data["terms"]), 0)

    def test_each_terminology_entry_has_official_provenance(self) -> None:
        # Given a terminology registry grounded in Blizzard localizations
        document = json.loads(TERMINOLOGY_PATH.read_text(encoding="utf-8"))

        # When every stored term is inspected
        entries = [
            entry
            for locale in document["locales"].values()
            for entry in locale["terms"].values()
        ]

        # Then no term can exist without a direct Blizzard source and review date
        self.assertGreater(len(entries), 0)
        for entry in entries:
            with self.subTest(entry=entry):
                self.assertTrue(entry["localized"].strip())
                self.assertIn(
                    entry["type"],
                    {"class", "specialization", "ability", "dungeon", "raid", "boss"},
                )
                self.assertRegex(
                    entry["sourceUrl"],
                    r"^https://(?:news|worldofwarcraft)\.blizzard\.com/",
                )
                self.assertRegex(entry["reviewedAt"], r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
