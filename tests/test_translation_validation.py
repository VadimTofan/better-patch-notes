import importlib.util
import json
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "scripts"
    / "validate_translations.py"
)
TERMINOLOGY_PATH = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "references"
    / "terminology.json"
)


def _load_validator_module():
    specification = importlib.util.spec_from_file_location(
        "validate_translations",
        VALIDATOR_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load validate_translations.py")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)

    return module


def _translation_batch() -> dict[str, object]:
    source_url = "https://news.blizzard.com/en-us/example"

    return {
        "changes": [
            {
                "category": "Class",
                "localizations": {
                    "en": {
                        "name": "Druid",
                        "specialization": "All",
                        "change": [
                            "Moonfire damage increased by 12.5% for 8 seconds."
                        ],
                        "source": "Blizzard",
                        "sourceUrl": source_url,
                        "translationType": "official",
                        "translatedFrom": "",
                        "terminologySourceUrls": [],
                    },
                    "ruRU": {
                        "name": "Друид",
                        "specialization": "All",
                        "change": [
                            "Урон от Moonfire увеличен на 12,5% на 8 секунд."
                        ],
                        "source": "Blizzard",
                        "sourceUrl": source_url,
                        "translationType": "agent",
                        "translatedFrom": "en",
                        "terminologySourceUrls": [
                            "https://worldofwarcraft.blizzard.com/ru-ru/game/classes/druid"
                        ],
                        "uncertainTerms": ["Moonfire"],
                    },
                },
            }
        ]
    }


# Describe: deterministic validation of grounded patch-note translations
class TranslationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _load_validator_module()
        self.terminology = json.loads(
            TERMINOLOGY_PATH.read_text(encoding="utf-8")
        )

    def test_accepts_grounded_translation_and_reports_fallbacks(self) -> None:
        # Given one grounded Russian translation with an English ability fallback
        batch = _translation_batch()

        # When the translation batch is validated
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then the locale, fallbacks, and uncertain English term are explicit
        self.assertEqual(("ruRU",), report.validated_locales)
        self.assertNotIn("ruRU", report.fallback_locales)
        self.assertIn("deDE", report.fallback_locales)
        self.assertEqual(("ruRU: Moonfire",), report.uncertain_terms)

    def test_rejects_a_translation_with_a_missing_bullet(self) -> None:
        # Given English notes with two bullets and a one-bullet translation
        batch = _translation_batch()
        english = batch["changes"][0]["localizations"]["en"]
        english["change"].append("Healing increased by 5%.")

        # When validation compares bullet alignment
        # Then the incomplete locale is rejected
        with self.assertRaisesRegex(ValueError, "bullet count"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_an_unverified_class_heading_left_in_english(self) -> None:
        # Given a class record whose unknown heading remains English
        batch = _translation_batch()
        english = batch["changes"][0]["localizations"]["en"]
        russian = batch["changes"][0]["localizations"]["ruRU"]
        english["name"] = "Chronomancer"
        russian["name"] = "Chronomancer"

        # When / Then class navigation terminology remains a hard blocker
        with self.assertRaisesRegex(
            ValueError,
            "unverified class terminology",
        ):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_changed_numeric_meaning(self) -> None:
        # Given a translation that changes 12.5% to 15%
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Moonfire увеличен на 15% на 8 секунд."
        ]

        # When numeric tokens are compared
        # Then the semantic mismatch is rejected
        with self.assertRaisesRegex(ValueError, "numeric values"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_reversed_change_direction(self) -> None:
        # Given an increase is translated as a decrease
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Moonfire уменьшен на 12,5% на 8 секунд."
        ]

        # When / Then the reversed semantic direction is rejected
        with self.assertRaisesRegex(ValueError, "change direction"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_a_lost_condition(self) -> None:
        # Given the English bullet has a condition missing from the translation
        batch = _translation_batch()
        english = batch["changes"][0]["localizations"]["en"]
        russian = batch["changes"][0]["localizations"]["ruRU"]
        english["change"] = [
            "Moonfire damage increased by 12.5% when active for 8 seconds."
        ]
        russian["change"] = [
            "Урон от Moonfire увеличен на 12,5% на 8 секунд."
        ]

        # When / Then the missing condition remains a release blocker
        with self.assertRaisesRegex(ValueError, "condition"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_an_altered_protected_uncertain_term(self) -> None:
        # Given an uncertain ability name is altered in the translated bullet
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Lunar Fire увеличен на 12,5% на 8 секунд."
        ]

        # When / Then preserved English fallback terminology is enforced
        with self.assertRaisesRegex(ValueError, "must remain"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_accepts_locale_spacing_before_a_percent_sign(self) -> None:
        # Given a translation using standard localized spacing before percent
        english = "Moonfire damage increased by 12.5% for 8 seconds."
        localized = "Moonfire: 12,5 % durante 8 segundos."

        # When numeric meaning is validated
        english_tokens = self.validator._numeric_tokens(english)
        localized_tokens = self.validator._numeric_tokens(localized)

        # Then typographic spacing does not count as a changed percentage
        self.assertEqual(
            english_tokens,
            localized_tokens,
        )

    def test_accepts_chinese_text_immediately_before_a_number(self) -> None:
        # Given Chinese typography without a space before percentages
        english = "Damage increased by 10% and then by 30%."
        localized = "伤害增加10%，然后增加30%。"

        # When numeric meaning is extracted
        english_tokens = self.validator._numeric_tokens(english)
        localized_tokens = self.validator._numeric_tokens(localized)

        # Then adjacent Chinese characters do not hide the numeric tokens
        self.assertEqual(english_tokens, localized_tokens)

    def test_accepts_numeric_reordering_required_by_target_grammar(self) -> None:
        # Given a translation that preserves every value in grammatical order
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "В течение 8 секунд урон от Moonfire увеличен на 12,5%."
        ]

        # When the complete translation is validated
        try:
            report = self.validator.validate_translation_batch(
                batch,
                self.terminology,
            )
        except ValueError as error:
            self.fail(f"numeric reordering was rejected: {error}")

        # Then the locale remains valid because no numeric meaning was lost
        self.assertEqual(("ruRU",), report.validated_locales)

    def test_rejects_an_unverified_localized_class_name(self) -> None:
        # Given a Russian class name that disagrees with the official glossary
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["name"] = "Друидка"

        # When terminology is checked
        # Then the unsupported localized term is rejected
        with self.assertRaisesRegex(ValueError, "expected Друид"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_missing_agent_provenance(self) -> None:
        # Given generated text without official terminology references
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["terminologySourceUrls"] = []

        # When provenance is checked
        # Then the generated translation is rejected
        with self.assertRaisesRegex(ValueError, "terminologySourceUrls"):
            self.validator.validate_translation_batch(batch, self.terminology)


if __name__ == "__main__":
    unittest.main()
