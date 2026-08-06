import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "mcp_server"
)
SERVICE_PATH = MCP_ROOT / "service.py"


def _load_service_module():
    if not SERVICE_PATH.exists():
        return None

    sys.path.insert(0, str(MCP_ROOT))
    specification = importlib.util.spec_from_file_location(
        "translation_mcp_service",
        SERVICE_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load translation MCP service")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _canonical_document() -> dict[str, object]:
    source_url = "https://news.blizzard.com/en-us/example"
    return {
        "schemaVersion": 5,
        "updatedAt": "2026-08-02T19:00:00+02:00",
        "changes": [
            {
                "id": "change-one",
                "channel": "live",
                "category": "Class",
                "date": "2026-08-02",
                "patch": "12.0.7",
                "localizations": {
                    "en": {
                        "name": "Druid",
                        "specialization": "Balance",
                        "change": ["Moonfire damage increased by 5%."],
                        "source": "Blizzard",
                        "sourceUrl": source_url,
                        "translationType": "official",
                        "translatedFrom": "",
                        "terminologySourceUrls": [],
                    },
                    "deDE": {
                        "name": "Druide",
                        "specialization": "Gleichgewicht",
                        "change": ["Moonfire-Schaden wurde um 5% erhöht."],
                        "source": "Blizzard",
                        "sourceUrl": source_url,
                        "translationType": "agent",
                        "translatedFrom": "en",
                        "terminologySourceUrls": [
                            "https://worldofwarcraft.blizzard.com/de-de/game/classes/druid"
                        ],
                    },
                },
            }
        ],
    }


def _terminology_document() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "locales": {
            "deDE": {
                "terms": {
                    "Druid": {
                        "localized": "Druide",
                        "type": "class",
                        "sourceUrl": "https://worldofwarcraft.blizzard.com/de-de/game/classes/druid",
                        "reviewedAt": "2026-08-02",
                    },
                    "Balance": {
                        "localized": "Gleichgewicht",
                        "type": "specialization",
                        "sourceUrl": "https://worldofwarcraft.blizzard.com/de-de/game/classes/druid",
                        "reviewedAt": "2026-08-02",
                    },
                }
            }
        },
    }


# Describe: locale preparation and official terminology staging
class TranslationMcpServicePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service_module = _load_service_module()
        self.assertIsNotNone(self.service_module)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.canonical_path = self.root / "retail-patch-notes.json"
        self.terminology_path = self.root / "terminology.json"
        self.work_dir = self.root / ".bpn-work"
        self.canonical_path.write_text(
            json.dumps(_canonical_document(), ensure_ascii=False),
            encoding="utf-8",
        )
        self.terminology_path.write_text(
            json.dumps(_terminology_document(), ensure_ascii=False),
            encoding="utf-8",
        )
        self.service = self.service_module.TranslationService(
            canonical_path=self.canonical_path,
            terminology_path=self.terminology_path,
            work_dir=self.work_dir,
        )

    def test_prepare_locale_returns_english_existing_text_and_terms(self) -> None:
        # Given canonical English and existing German patch-note text

        # When German preparation data is requested
        prepared = self.service.prepare_locale("deDE")

        # Then Codex receives aligned source, comparison, and terminology data
        self.assertEqual("deDE", prepared["locale"])
        self.assertEqual(1, len(prepared["records"]))
        record = prepared["records"][0]
        self.assertEqual("change-one", record["id"])
        self.assertEqual(
            ["Moonfire damage increased by 5%."],
            record["english"]["change"],
        )
        self.assertEqual(
            ["Moonfire-Schaden wurde um 5% erhöht."],
            record["existing"]["change"],
        )
        self.assertEqual("Druide", prepared["terminology"]["Druid"]["localized"])

    def test_prepare_locale_rejects_an_unsupported_locale(self) -> None:
        # Given a locale outside the addon's canonical locale set
        # When preparation is requested
        # Then the service rejects it instead of creating a new locale
        with self.assertRaisesRegex(ValueError, "unsupported locale"):
            self.service.prepare_locale("plPL")

    def test_record_terminology_stages_verified_blizzard_terms(self) -> None:
        # Given a verified German ability name from an official Blizzard page
        terms = [
            {
                "english": "Moonfire",
                "localized": "Mondfeuer",
                "type": "ability",
                "sourceUrl": "https://worldofwarcraft.blizzard.com/de-de/game/classes/druid",
                "reviewedAt": "2026-08-02",
            }
        ]

        # When the terminology evidence is recorded
        result = self.service.record_terminology("deDE", terms)

        # Then it is staged without changing the canonical terminology file
        self.assertEqual(1, result["recorded"])
        state = self.service.workspace.load()
        staged = state["terminology"]["deDE"]["Moonfire"]
        self.assertEqual("Mondfeuer", staged["localized"])
        canonical = json.loads(self.terminology_path.read_text(encoding="utf-8"))
        self.assertNotIn("Moonfire", canonical["locales"]["deDE"]["terms"])

    def test_record_terminology_rejects_non_blizzard_provenance(self) -> None:
        # Given terminology found only on an untrusted secondary site
        terms = [
            {
                "english": "Moonfire",
                "localized": "Mondfeuer",
                "type": "ability",
                "sourceUrl": "https://example.com/moonfire",
                "reviewedAt": "2026-08-02",
            }
        ]

        # When the unsupported evidence is recorded
        # Then it is rejected before workspace state changes
        with self.assertRaisesRegex(ValueError, "Blizzard URL"):
            self.service.record_terminology("deDE", terms)

    def test_record_terminology_accepts_a_sourced_boss_name(self) -> None:
        # Given a boss name verified in official localized raid notes
        terms = [
            {
                "english": "Dimensius",
                "localized": "Dimensius",
                "type": "boss",
                "sourceUrl": "https://news.blizzard.com/de-de/example",
                "reviewedAt": "2026-08-02",
            }
        ]

        # When the terminology evidence is recorded
        result = self.service.record_terminology("deDE", terms)

        # Then the supported WoW term type is staged
        self.assertEqual(1, result["recorded"])


# Describe: locale submission, audit, comparison, and finalization
class TranslationMcpServiceWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service_module = _load_service_module()
        self.assertIsNotNone(self.service_module)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.canonical_path = self.root / "retail-patch-notes.json"
        self.terminology_path = self.root / "terminology.json"
        self.work_dir = self.root / ".bpn-work"
        self.canonical_path.write_text(
            json.dumps(_canonical_document(), ensure_ascii=False),
            encoding="utf-8",
        )
        self.terminology_path.write_text(
            json.dumps(_terminology_document(), ensure_ascii=False),
            encoding="utf-8",
        )
        self.original_canonical = self.canonical_path.read_bytes()
        self.service = self.service_module.TranslationService(
            canonical_path=self.canonical_path,
            terminology_path=self.terminology_path,
            work_dir=self.work_dir,
        )

    @staticmethod
    def _german_record(change: str | None = None) -> dict[str, object]:
        return {
            "id": "change-one",
            "name": "Druide",
            "specialization": "Gleichgewicht",
            "change": [
                change or "Der Schaden von Mondfeuer wurde um 5% erhöht."
            ],
            "translationType": "agent",
            "translatedFrom": "en",
            "terminologySourceUrls": [
                "https://worldofwarcraft.blizzard.com/de-de/game/classes/druid"
            ],
            "uncertainTerms": [],
        }

    def test_submit_audit_compare_and_status_complete_one_locale(self) -> None:
        # Given a complete German translation for the current source snapshot
        self.service.submit_locale("deDE", [self._german_record()])

        # When it is audited and compared
        audit = self.service.audit_locale("deDE")
        comparison = self.service.compare_locale("deDE")
        status = self.service.translation_status()

        # Then the locale passes and remains aligned with English by record ID
        self.assertTrue(audit["passed"])
        self.assertEqual("change-one", comparison["records"][0]["id"])
        self.assertEqual(
            ["Moonfire damage increased by 5%."],
            comparison["records"][0]["english"]["change"],
        )
        self.assertEqual("passed", status["locales"]["deDE"]["status"])

    def test_failed_audit_keeps_locale_in_needs_review(self) -> None:
        # Given a German translation that changes the numeric value
        self.service.submit_locale(
            "deDE",
            [self._german_record("Der Schaden wurde um 7% erhöht.")],
        )

        # When the locale is audited
        audit = self.service.audit_locale("deDE")

        # Then it is blocked for review
        self.assertFalse(audit["passed"])
        self.assertEqual(
            "needs-review",
            self.service.translation_status()["locales"]["deDE"]["status"],
        )

    def test_unverified_localized_heading_fails_the_audit(self) -> None:
        # Given an agent invents a class name that conflicts with the registry
        record = self._german_record()
        record["name"] = "Druidisch"
        self.service.submit_locale("deDE", [record])

        # When the grounded locale audit runs
        audit = self.service.audit_locale("deDE")

        # Then the unverified heading blocks completion
        self.assertFalse(audit["passed"])
        failed_checks = {
            finding["check"]
            for report in audit["records"]
            for finding in report["findings"]
        }
        self.assertIn("name_localized", failed_checks)

    def test_official_locale_keeps_its_localized_blizzard_source(self) -> None:
        # Given current German text published on the localized Blizzard site
        official_record = self._german_record()
        official_record.update(
            {
                "translationType": "official",
                "translatedFrom": "",
                "sourceUrl": "https://news.blizzard.com/de-de/example",
                "terminologySourceUrls": [],
            }
        )

        # When the official locale is submitted and audited
        self.service.submit_locale(
            "deDE",
            [official_record],
            outcome="official",
        )
        audit = self.service.audit_locale("deDE")

        # Then it passes and retains the localized official source URL
        self.assertTrue(audit["passed"])
        localized = self.service.compare_locale("deDE")["records"][0][
            "localized"
        ]
        self.assertEqual(
            "https://news.blizzard.com/de-de/example",
            localized["sourceUrl"],
        )

    def test_english_fallback_requires_a_documented_reason(self) -> None:
        # Given a locale without a safe official or agent translation
        # When fallback is submitted without a reason
        # Then classification is rejected
        with self.assertRaisesRegex(ValueError, "fallback reason"):
            self.service.submit_locale(
                "frFR",
                [],
                outcome="english-fallback",
            )

    def test_finalize_requires_every_locale_to_be_classified(self) -> None:
        # Given only German has completed review
        self.service.submit_locale("deDE", [self._german_record()])
        self.service.audit_locale("deDE")

        # When finalization is requested
        # Then the incomplete locale matrix blocks output
        with self.assertRaisesRegex(ValueError, "incomplete locales"):
            self.service.finalize_translations()

    def test_finalize_reaudits_passed_state_before_writing_outputs(self) -> None:
        # Given a passed locale whose staged file was later corrupted
        self.service.submit_locale("deDE", [self._german_record()])
        self.service.audit_locale("deDE")
        state = self.service.workspace.load()
        state["locales"]["deDE"]["records"]["change-one"]["change"] = [
            "Der Schaden wurde um 9% erhöht."
        ]
        self.service.workspace.save(state)
        for locale in self.service_module.SUPPORTED_TRANSLATION_LOCALES:
            if locale != "deDE":
                self.service.submit_locale(
                    locale,
                    [],
                    outcome="english-fallback",
                    fallback_reason="No safe localized terminology was found.",
                )

        # When finalization performs its last review gate
        # Then stale passed status cannot bypass the numeric audit
        with self.assertRaisesRegex(ValueError, "failed final audit"):
            self.service.finalize_translations()

    def test_finalize_writes_staged_outputs_without_mutating_canonical_data(self) -> None:
        # Given German passed and every other locale has a documented fallback
        self.service.submit_locale("deDE", [self._german_record()])
        self.service.audit_locale("deDE")
        for locale in self.service_module.SUPPORTED_TRANSLATION_LOCALES:
            if locale != "deDE":
                self.service.submit_locale(
                    locale,
                    [],
                    outcome="english-fallback",
                    fallback_reason="No safe localized terminology was found.",
                )

        # When the completed matrix is finalized
        result = self.service.finalize_translations()

        # Then atomic batch artifacts are produced and canonical data is intact
        self.assertTrue(Path(result["batchPath"]).exists())
        self.assertTrue(Path(result["terminologyPath"]).exists())
        self.assertEqual(self.original_canonical, self.canonical_path.read_bytes())
        batch = json.loads(Path(result["batchPath"]).read_text(encoding="utf-8"))
        german = batch["changes"][0]["localizations"]["deDE"]
        self.assertEqual("Druide", german["name"])
        self.assertEqual(9, len(batch["localeCompletion"]["fallbacks"]))


if __name__ == "__main__":
    unittest.main()
