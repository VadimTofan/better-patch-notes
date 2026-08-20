from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from automation.aggregate_translations import (
    aggregate_locale_artifacts,
    run_aggregation,
)
from automation.coordinator import SUPPORTED_TRANSLATION_LOCALES


def _english_document() -> dict[str, object]:
    return {
        "schemaVersion": 5,
        "updatedAt": "2026-08-20T04:07:00+00:00",
        "changes": [
            {
                "channel": "live",
                "category": "Class",
                "date": "2026-08-19",
                "patch": "12.1.0",
                "localizations": {
                    "en": {
                        "name": "Druid",
                        "specialization": "Restoration",
                        "change": ["Fixed Rejuvenation."],
                        "source": "Blizzard",
                        "sourceUrl": "https://news.blizzard.com/example",
                        "translationType": "official",
                        "translatedFrom": "",
                        "terminologySourceUrls": [],
                    }
                },
            }
        ],
    }


def _locale_artifact(locale: str) -> dict[str, object]:
    batch = deepcopy(_english_document())
    batch["retrievedAt"] = batch.pop("updatedAt")
    batch["changes"][0]["localizations"][locale] = {
        "name": "Druid",
        "specialization": "Restoration",
        "change": [f"{locale} translation"],
        "source": "Blizzard",
        "sourceUrl": "https://news.blizzard.com/example",
        "translationType": "agent",
        "translatedFrom": "en",
        "terminologySourceUrls": ["https://news.blizzard.com/example"],
        "protectedTerms": [],
        "uncertainTerms": [],
    }
    return {
        "locale": locale,
        "status": "PASS",
        "reason": "",
        "uncertainTerms": [],
        "batch": batch,
    }


# Describe: fail-closed translation artifact aggregation
class AggregateTranslationsTests(unittest.TestCase):
    def test_malformed_acquisition_writes_a_blocked_audit(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given the acquisition artifact contains malformed JSON
            root = Path(temporary_directory)
            acquisition = root / "acquisition"
            translations = root / "translations"
            result_path = root / "automation-result.json"
            acquisition.mkdir()
            translations.mkdir()
            (acquisition / "english-document.json").write_text(
                "{invalid",
                encoding="utf-8",
            )

            # When aggregation attempts to load the artifacts
            exit_code = run_aggregation(
                acquisition_directory=acquisition,
                translations_directory=translations,
                result_path=result_path,
                dry_run=True,
            )

            # Then it fails closed and retains a diagnostic result
            self.assertEqual(1, exit_code)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual("BLOCKED", result["status"])
            self.assertIn("Expecting property name", result["reason"])

    def test_merges_exactly_one_passing_artifact_for_every_locale(self) -> None:
        # Given all ten locale workers passed against the same English data
        english = _english_document()
        artifacts = tuple(
            _locale_artifact(locale)
            for locale in sorted(SUPPORTED_TRANSLATION_LOCALES)
        )

        # When locale artifacts are aggregated
        combined = aggregate_locale_artifacts(english, artifacts)

        # Then every locale and English appear in the one atomic batch
        localizations = combined["changes"][0]["localizations"]
        self.assertEqual(
            {"en", *SUPPORTED_TRANSLATION_LOCALES},
            set(localizations),
        )
        self.assertEqual("", combined["changes"][0]["replacesSourceUrl"])
        self.assertNotIn("uncertainTerms", combined)

    def test_rejects_a_missing_locale_artifact(self) -> None:
        # Given one required locale has no artifact
        english = _english_document()
        locales = sorted(SUPPORTED_TRANSLATION_LOCALES)[:-1]
        artifacts = tuple(_locale_artifact(locale) for locale in locales)

        # When / Then aggregation fails closed
        with self.assertRaisesRegex(ValueError, "missing locale artifacts"):
            aggregate_locale_artifacts(english, artifacts)

    def test_rejects_a_failed_locale_artifact(self) -> None:
        # Given one locale worker reported failure
        english = _english_document()
        artifacts = [
            _locale_artifact(locale)
            for locale in sorted(SUPPORTED_TRANSLATION_LOCALES)
        ]
        artifacts[0]["status"] = "FAILED"
        artifacts[0]["reason"] = "Gemini timed out"

        # When / Then the unsafe partial batch is rejected
        with self.assertRaisesRegex(ValueError, "Gemini timed out"):
            aggregate_locale_artifacts(english, tuple(artifacts))


if __name__ == "__main__":
    unittest.main()
