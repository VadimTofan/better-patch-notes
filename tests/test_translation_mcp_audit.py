import importlib.util
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = PROJECT_ROOT / "skills" / "translate-patch-notes" / "mcp_server"
AUDIT_PATH = MCP_ROOT / "audit.py"


def _load_audit_module():
    if not AUDIT_PATH.exists():
        return None

    sys.path.insert(0, str(MCP_ROOT))
    specification = importlib.util.spec_from_file_location(
        "translation_mcp_audit",
        AUDIT_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load translation MCP audit")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _english() -> dict[str, object]:
    return {
        "name": "Druid",
        "specialization": "Balance",
        "change": ["Moonfire damage increased by 5% for 10 seconds."],
        "sourceUrl": "https://news.blizzard.com/en-us/example",
    }


def _german() -> dict[str, object]:
    return {
        "name": "Druide",
        "specialization": "Gleichgewicht",
        "change": [
            "Der Schaden von Mondfeuer wurde 10 Sekunden lang um 5% erhöht."
        ],
        "sourceUrl": "https://news.blizzard.com/en-us/example",
        "translationType": "agent",
        "translatedFrom": "en",
        "terminologySourceUrls": [
            "https://worldofwarcraft.blizzard.com/de-de/game/classes/druid"
        ],
        "uncertainTerms": [],
    }


# Describe: deterministic 30-check locale audit
class TranslationMcpAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit_module = _load_audit_module()
        self.assertIsNotNone(self.audit_module)

    def test_complete_translation_passes_all_thirty_checks(self) -> None:
        # Given a structurally complete German translation
        # When the locale audit runs
        report = self.audit_module.audit_translation(
            "deDE",
            _english(),
            _german(),
        )

        # Then all 30 named checks pass
        self.assertEqual(30, len(report["checks"]))
        self.assertTrue(report["passed"])
        self.assertEqual([], report["findings"])

    def test_changed_number_and_english_leakage_block_the_locale(self) -> None:
        # Given a translation with a changed number and English prose
        localized = _german()
        localized["change"] = [
            "Moonfire damage increased by 7% für 10 Sekunden."
        ]

        # When the locale audit runs
        report = self.audit_module.audit_translation(
            "deDE",
            _english(),
            localized,
        )

        # Then the numeric and English-leakage checks fail
        self.assertFalse(report["passed"])
        failed_checks = {
            finding["check"] for finding in report["findings"]
        }
        self.assertIn("numeric_values", failed_checks)
        self.assertIn("english_3gram", failed_checks)

    def test_missing_semantic_direction_blocks_the_locale(self) -> None:
        # Given a translation that preserves values but loses "increased"
        localized = _german()
        localized["change"] = [
            "Der Schaden von Mondfeuer beträgt 10 Sekunden lang 5%."
        ]

        # When the locale audit runs
        report = self.audit_module.audit_translation(
            "deDE",
            _english(),
            localized,
        )

        # Then the increase-direction check fails
        self.assertFalse(report["passed"])
        failed_checks = {
            finding["check"] for finding in report["findings"]
        }
        self.assertIn("increase_direction", failed_checks)

    def test_copied_regional_agent_translation_requires_review(self) -> None:
        # Given identical agent text submitted for both Spanish regions
        localized = {
            "name": "Druida",
            "specialization": "Equilibrio",
            "change": [
                "El daño de Fuego lunar aumentó un 5% durante 10 segundos."
            ],
            "sourceUrl": "https://news.blizzard.com/en-us/example",
            "translationType": "agent",
            "translatedFrom": "en",
            "terminologySourceUrls": [
                "https://worldofwarcraft.blizzard.com/es-es/game/classes/druid"
            ],
            "uncertainTerms": [],
        }

        # When the regional duplication audit runs
        report = self.audit_module.audit_translation(
            "esES",
            _english(),
            localized,
            regional_peer=localized,
        )

        # Then copied regional prose is sent back for independent review
        self.assertFalse(report["passed"])
        failed_checks = {
            finding["check"] for finding in report["findings"]
        }
        self.assertIn("regional_duplicate", failed_checks)

    def test_matching_official_regional_text_is_allowed(self) -> None:
        # Given Blizzard independently published matching text for both regions
        localized = {
            "name": "Druida",
            "specialization": "Equilibrio",
            "change": [
                "El daño de Fuego lunar aumentó un 5% durante 10 segundos."
            ],
            "sourceUrl": "https://news.blizzard.com/es-es/example",
            "translationType": "official",
            "translatedFrom": "",
            "terminologySourceUrls": [],
            "uncertainTerms": [],
        }

        # When the audit compares the separately sourced regional records
        report = self.audit_module.audit_translation(
            "esES",
            _english(),
            localized,
            regional_peer=localized,
        )

        # Then official provenance prevents a false copied-text failure
        self.assertTrue(report["passed"])


if __name__ == "__main__":
    unittest.main()
