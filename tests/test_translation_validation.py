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
                            "Урон от Лунный огонь увеличен на 12,5% на 8 секунд."
                        ],
                        "source": "Blizzard",
                        "sourceUrl": source_url,
                        "translationType": "agent",
                        "translatedFrom": "en",
                        "terminologySourceUrls": [
                            "https://worldofwarcraft.blizzard.com/ru-ru/game/classes/druid"
                        ],
                    },
                },
            }
        ]
    }


# Describe: deterministic validation of grounded patch-note translations
class TranslationValidationTests(unittest.TestCase):
    def test_classifies_only_the_requested_locale(self) -> None:
        # Given a valid Russian localization and no other locales
        module = _load_validator_module()
        batch = _translation_batch()
        terminology = json.loads(TERMINOLOGY_PATH.read_text(encoding="utf-8"))

        # When classification targets Russian only
        report = module.classify_translation_batch(
            batch,
            terminology,
            target_locale="ruRU",
        )

        # Then unrelated locales are not reported as fallbacks
        self.assertEqual(("ruRU",), report.validated_locales)
        self.assertEqual((), report.fallback_locales)
        self.assertEqual({}, report.fallback_reasons)

    def setUp(self) -> None:
        self.validator = _load_validator_module()
        self.terminology = json.loads(
            TERMINOLOGY_PATH.read_text(encoding="utf-8")
        )
        self.terminology["locales"]["ruRU"]["terms"]["Moonfire"] = {
            "localized": "Лунный огонь",
            "type": "ability",
            "sourceUrl": (
                "https://worldofwarcraft.blizzard.com/ru-ru/game/classes/druid"
            ),
            "reviewedAt": "2026-08-13",
        }

    def test_accepts_grounded_translation_and_reports_fallbacks(self) -> None:
        # Given one grounded Russian translation with verified terminology
        batch = _translation_batch()

        # When the translation batch is validated
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then the locale and documented generation fallback are explicit
        self.assertEqual(("ruRU",), report.validated_locales)
        self.assertNotIn("ruRU", report.fallback_locales)
        self.assertIn("deDE", report.fallback_locales)
        self.assertEqual((), report.uncertain_terms)

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
        russian["protectedTerms"] = ["Chronomancer"]

        # When / Then class navigation terminology remains a hard blocker
        with self.assertRaisesRegex(
            ValueError,
            "unverified terminology",
        ):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_accepts_a_verified_class_heading_preserved_in_english(self) -> None:
        # Given a known class heading follows the English-name policy
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["name"] = "Druid"

        # When the grounded translation is validated
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then preserving the verified class name does not block the locale
        self.assertIn("ruRU", report.validated_locales)

    def test_reports_a_preserved_unverified_ability_as_a_warning(self) -> None:
        # Given an ability name remains English without verified terminology
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Moonfire увеличен на 12,5% на 8 секунд."
        ]
        russian["trustedCanonical"] = True
        russian["uncertainTerms"] = ["Moonfire"]

        # When the exact ability is preserved in translated prose
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then it is auditable without being mistaken for English prose
        self.assertEqual(("ruRU: Moonfire",), report.uncertain_terms)

    def test_rejects_an_unverified_agent_translated_russian_heading(self) -> None:
        # Given Russian invents a translation for an unknown class heading
        batch = _translation_batch()
        english = batch["changes"][0]["localizations"]["en"]
        russian = batch["changes"][0]["localizations"]["ruRU"]
        english["name"] = "Chronomancer"
        russian["name"] = "Хрономант"

        # When / Then agent wording cannot verify game terminology
        with self.assertRaisesRegex(
            ValueError,
            "unverified class terminology",
        ):
            self.validator.validate_translation_batch(
                batch,
                self.terminology,
            )

    def test_rejects_english_leakage_in_simplified_chinese(self) -> None:
        # Given an otherwise translated Chinese bullet leaves English prose
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"].pop("ruRU")
        chinese = dict(russian)
        chinese["name"] = "德鲁伊"
        chinese["change"] = [
            "Moonfire damage 伤害提高 12.5%，持续 8 秒。"
        ]
        batch["changes"][0]["localizations"]["zhCN"] = chinese

        # When / Then untranslated English is a hard blocker
        with self.assertRaisesRegex(ValueError, "English leakage"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_accepts_verified_english_game_terms_in_translated_prose(self) -> None:
        # Given verified class and ability names intentionally remain English
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["name"] = "Druid"
        russian["change"] = [
            "Урон от Moonfire увеличен на 12,5% на 8 секунд."
        ]
        russian["trustedCanonical"] = True

        # When the translated prose is validated
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then exact registry-grounded game terms need no legacy metadata
        self.assertEqual(("ruRU",), report.validated_locales)

    def test_rejects_english_prose_outside_verified_game_terms(self) -> None:
        # Given a verified ability is followed by untranslated English prose
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["name"] = "Druid"
        russian["change"] = [
            "Moonfire damage increased на 12,5% на 8 секунд."
        ]
        russian["protectedTerms"] = ["Druid", "Moonfire"]

        # When / Then only the protected name is exempt from leakage checks
        with self.assertRaisesRegex(ValueError, "English leakage"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_rejects_changed_numeric_meaning(self) -> None:
        # Given a translation that changes 12.5% to 15%
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Лунный огонь увеличен на 15% на 8 секунд."
        ]

        # When numeric tokens are compared
        # Then the semantic mismatch is rejected
        with self.assertRaisesRegex(ValueError, "numeric values"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_classifies_an_invalid_locale_as_a_documented_fallback(self) -> None:
        # Given one locale changes a protected numeric value
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Лунный огонь увеличен на 15% на 8 секунд."
        ]

        # When the batch is classified for automatic publication
        report = self.validator.classify_translation_batch(
            batch,
            self.terminology,
        )

        # Then that locale receives a reasoned English fallback
        self.assertIn("ruRU", report.fallback_locales)
        self.assertNotIn("ruRU", report.validated_locales)
        self.assertIn("numeric values", report.fallback_reasons["ruRU"])

    def test_preserves_a_generation_fallback_reason(self) -> None:
        # Given a locale was omitted because automatic generation failed
        batch = _translation_batch()
        del batch["changes"][0]["localizations"]["ruRU"]
        batch["fallbackReasons"] = {
            "ruRU": "automatic translation generation failed",
        }

        # When the incomplete batch is classified
        report = self.validator.classify_translation_batch(
            batch,
            self.terminology,
        )

        # Then the release report retains the exact safe fallback reason
        self.assertEqual(
            "automatic translation generation failed",
            report.fallback_reasons["ruRU"],
        )

    def test_rejects_reversed_change_direction(self) -> None:
        # Given an increase is translated as a decrease
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Лунный огонь уменьшен на 12,5% на 8 секунд."
        ]

        # When / Then the reversed semantic direction is rejected
        with self.assertRaisesRegex(ValueError, "change direction"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_accepts_the_irregular_spanish_redujo_direction(self) -> None:
        # Given Spanish correctly uses the irregular preterite "redujo"
        english = "Damage bonus reduced to 5% per stack (was 6%)."
        localized = (
            "La bonificación de daño se redujo a 5% por acumulación "
            "(antes 6%)."
        )

        # When the aligned direction is checked
        try:
            self.validator._validate_semantic_structure(
                "esMX",
                1,
                english,
                localized,
            )
        except ValueError as error:
            self.fail(f"valid Spanish reduction was rejected: {error}")

    def test_accepts_chinese_duration_extension_as_an_increase(self) -> None:
        # Given a duration increase uses the natural Chinese verb for extension
        english = "Duration increased to 10 seconds (was 6 seconds)."
        localized = "持续时间延长至10秒（原为6秒）。"

        # When the aligned direction is checked
        try:
            self.validator._validate_semantic_structure(
                "zhCN",
                1,
                english,
                localized,
            )
        except ValueError as error:
            # Then the valid increase wording must not be rejected
            self.fail(f"valid Chinese extension was rejected: {error}")

    def test_accepts_majority_approved_semantic_synonym(self) -> None:
        # Given two independent judges approved a valid unlisted Russian synonym
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Лунный огонь стал больше на 12,5% на 8 секунд."
        ]
        batch["semanticApprovals"] = [{
            "change": 0,
            "locale": "ruRU",
            "bullet": 0,
        }]

        # When / Then the phrase-list semantic check accepts that coordinate
        self.validator.validate_translation_batch(batch, self.terminology)

    def test_semantic_approval_cannot_bypass_numeric_validation(self) -> None:
        # Given an approved coordinate still changes a protected numeric value
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Лунный огонь стал больше на 15% на 8 секунд."
        ]
        batch["semanticApprovals"] = [{
            "change": 0,
            "locale": "ruRU",
            "bullet": 0,
        }]

        # When / Then deterministic numeric validation remains authoritative
        with self.assertRaisesRegex(ValueError, "numeric"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_semantic_approval_cannot_bypass_english_leakage(self) -> None:
        # Given an approved coordinate still contains untranslated prose
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Лунный огонь increased на 12,5% на 8 секунд."
        ]
        batch["semanticApprovals"] = [{
            "change": 0,
            "locale": "ruRU",
            "bullet": 0,
        }]

        # When / Then untranslated English remains a hard release blocker
        with self.assertRaisesRegex(ValueError, "English leakage"):
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
            "Урон от Лунный огонь увеличен на 12,5% на 8 секунд."
        ]

        # When / Then the missing condition remains a release blocker
        with self.assertRaisesRegex(ValueError, "condition"):
            self.validator.validate_translation_batch(batch, self.terminology)

    def test_accepts_conditions_expressed_with_natural_locale_grammar(self) -> None:
        # Given equivalent conditions use idiomatic grammar instead of if/when
        examples = (
            (
                "deDE",
                "If you know Rend, strike.",
                "Beherrscht ihr 'Verwunden', schlagt zu.",
            ),
            (
                "deDE",
                "Damage applies when activating it.",
                "Schaden gilt beim Aktivieren.",
            ),
            (
                "frFR",
                "Damage fades while active.",
                "Les dégâts diminuent pendant son activation.",
            ),
            (
                "itIT",
                "The effect applies when used.",
                "L'effetto si applica all'utilizzo.",
            ),
            (
                "ptBR",
                "The effect applies when used.",
                "O efeito é aplicado ao ser usado.",
            ),
            (
                "frFR",
                "The effect applies when used.",
                "L’effet s’applique lors de son utilisation.",
            ),
            (
                "frFR",
                "The effect applies when used.",
                "L’effet s’applique à l’utilisation.",
            ),
            (
                "ptBR",
                "The effect applies when activated.",
                "O efeito é aplicado ao ativar a técnica.",
            ),
            (
                "ruRU",
                "Damage is reduced while Blood Shield is active.",
                "Урон снижен на время действия Blood Shield.",
            ),
            (
                "itIT",
                "If its healing would overheal, transfer the excess.",
                "Le sovracure si trasferiscono a un alleato.",
            ),
        )

        # When / Then each condition remains detectable
        for locale, english, localized in examples:
            with self.subTest(locale=locale):
                self.assertTrue(
                    self.validator._preserves_conditions(
                        locale,
                        english,
                        localized,
                    )
                )

    def test_accepts_reviewed_semantics_from_the_august_22_run(self) -> None:
        # Given valid localized semantics rejected by the August 22 dry run
        examples = (
            (
                "deDE",
                "Applied after casting while silenced.",
                "Nach dem Wirken im zum Schweigen gebrachten Zustand aktiv.",
            ),
            (
                "deDE",
                "Applied when used in tandem with Soul of the Forest.",
                "In Kombination mit Soul of the Forest angewendet.",
            ),
            (
                "esES",
                "Reduce damage while increasing area damage.",
                "Reduce el daño a la vez que aumenta el daño de área.",
            ),
            (
                "esES",
                "Applied after casting while silenced.",
                "Se aplicó tras lanzar bajo los efectos de silencio.",
            ),
            (
                "esES",
                "Reduce damage while increasing area damage.",
                "Reduce el daño al tiempo que aumenta el daño de área.",
            ),
            (
                "frFR",
                "Cast while talented into Unload.",
                "Lancé tout en ayant choisi le talent Unload.",
            ),
            (
                "itIT",
                "The buff was not consumed when casting an ability.",
                "Il buff non veniva consumato lanciando un'abilità.",
            ),
            (
                "koKR",
                "The radius decreases as the raid size increases.",
                "공격대 규모가 커질수록 반경이 점차 줄어듭니다.",
            ),
            (
                "koKR",
                "Activation rate increased by 33%.",
                "활성화 주기가 33%만큼 빨라졌습니다.",
            ),
            (
                "zhCN",
                "Damage was not properly reduced by reduction effects.",
                "伤害未被减伤效果正确减免。",
            ),
            (
                "zhCN",
                "The radius decreases as the raid size increases.",
                "半径随着团队规模的增加而逐渐减小。",
            ),
            (
                "zhTW",
                "Baseline damage has been increased.",
                "基礎傷害已調高。",
            ),
            (
                "zhTW",
                "Cast time reduced to 13 seconds (was 15 seconds).",
                "施法時間縮短至13秒（原為15秒）。",
            ),
            (
                "zhTW",
                "The radius decreases as the group size increases.",
                "半徑隨著團隊規模增加而逐漸縮小。",
            ),
        )

        # When each aligned bullet is checked
        for locale, english, localized in examples:
            with self.subTest(locale=locale):
                try:
                    self.validator._validate_semantic_structure(
                        locale,
                        1,
                        english,
                        localized,
                    )
                except ValueError as error:
                    # Then natural equivalent wording must remain publishable
                    self.fail(f"valid {locale} semantics rejected: {error}")

    def test_does_not_treat_an_ability_name_as_an_after_condition(self) -> None:
        # Given After the Wildfire is an ability name, not conditional prose
        english = "After the Wildfire healing increased by 25%."
        localized = "Die Heilung von 'Nach dem Lauffeuer' wurde erhöht."

        # When / Then the title does not create a condition requirement
        self.assertTrue(
            self.validator._preserves_conditions(
                "deDE",
                english,
                localized,
            )
        )

    def test_accepts_spanish_tras_for_an_after_condition(self) -> None:
        # Given a natural Spanish translation using "tras" for "after"
        english = "Removed Ghastly Brute after Mchimba the Embalmer."
        localized = (
            "Se eliminó Ghastly Brute tras Mchimba the Embalmer."
        )

        # When the aligned bullet is checked
        try:
            self.validator._validate_semantic_structure(
                "esES",
                1,
                english,
                localized,
            )
        except ValueError as error:
            self.fail(f"valid Spanish after-condition was rejected: {error}")

    def test_accepts_spanish_talent_context_for_a_while_condition(self) -> None:
        # Given "while talented" is naturally expressed as "con el talento"
        english = "Aimed Shot failed while talented into Aspect of the Hydra."
        localized = (
            "Aimed Shot fallaba con el talento Aspect of the Hydra."
        )

        # When the aligned bullet is checked
        try:
            self.validator._validate_semantic_structure(
                "esES",
                1,
                english,
                localized,
            )
        except ValueError as error:
            self.fail(f"valid Spanish while-condition was rejected: {error}")

    def test_accepts_korean_si_for_a_when_condition(self) -> None:
        # Given Korean expresses "when killing" as the construction "처치 시"
        english = "Items could be missing when killing the World Boss."
        localized = (
            "World Boss 처치 시 아이템을 받지 못할 수 있었습니다."
        )

        # When the aligned bullet is checked
        try:
            self.validator._validate_semantic_structure(
                "koKR",
                1,
                english,
                localized,
            )
        except ValueError as error:
            self.fail(f"valid Korean when-condition was rejected: {error}")

    def test_rejects_a_spanish_pattern_for_the_wrong_condition_type(self) -> None:
        # Given an after-condition is mistranslated as unrelated talent context
        english = "Removed Ghastly Brute after Mchimba the Embalmer."
        localized = (
            "Se eliminó Ghastly Brute con el talento Mchimba the Embalmer."
        )

        # When / Then source-aware validation rejects the wrong relationship
        with self.assertRaisesRegex(ValueError, "condition"):
            self.validator._validate_semantic_structure(
                "esES",
                1,
                english,
                localized,
            )

    def test_rejects_an_altered_protected_uncertain_term(self) -> None:
        # Given an uncertain ability name is altered in the translated bullet
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["change"] = [
            "Урон от Lunar Fire увеличен на 12,5% на 8 секунд."
        ]
        russian["uncertainTerms"] = ["Moonfire"]

        # When / Then unresolved terminology blocks publication
        with self.assertRaisesRegex(ValueError, "invalid uncertain term"):
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
            "В течение 8 секунд урон от Лунный огонь увеличен на 12,5%."
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

    def test_heading_term_may_be_localized_inside_patch_note_prose(self) -> None:
        # Given Blood is preserved as a specialization heading but translated
        # naturally when it appears inside an ability name in Chinese prose
        batch = _translation_batch()
        english = batch["changes"][0]["localizations"]["en"]
        russian = batch["changes"][0]["localizations"].pop("ruRU")
        english["name"] = "Death Knight"
        english["specialization"] = "Blood"
        english["change"] = ["Blood Plague healing increased by 25%."]
        chinese = dict(russian)
        chinese["name"] = "Death Knight"
        chinese["specialization"] = "Blood"
        chinese["change"] = ["血之瘟疫的治疗量提高 25%。"]
        chinese["protectedTerms"] = ["Death Knight", "Blood"]
        batch["changes"][0]["localizations"]["zhCN"] = chinese
        locale_terms = self.terminology["locales"]["zhCN"]["terms"]
        locale_terms["Death Knight"] = {
            "localized": "Death Knight",
            "sourceUrl": "https://worldofwarcraft.blizzard.com/en-us/game/classes/death-knight",
        }
        locale_terms["Blood"] = {
            "localized": "Blood",
            "sourceUrl": "https://worldofwarcraft.blizzard.com/en-us/game/classes/death-knight",
        }

        # When the prose is validated
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then the heading remains English without forcing prose to do so
        self.assertEqual(("zhCN",), report.validated_locales)

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

    def test_accepts_official_blizzard_forum_provenance(self) -> None:
        # Given an agent translation cites its reviewed Blizzard forum source
        batch = _translation_batch()
        russian = batch["changes"][0]["localizations"]["ruRU"]
        russian["sourceUrl"] = (
            "https://us.forums.blizzard.com/en/wow/t/notes/2336820/1"
        )
        russian["terminologySourceUrls"] = [russian["sourceUrl"]]
        batch["changes"][0]["localizations"]["en"]["sourceUrl"] = (
            russian["sourceUrl"]
        )

        # When provenance is validated
        report = self.validator.validate_translation_batch(
            batch,
            self.terminology,
        )

        # Then the direct official Blizzard forum URL is accepted
        self.assertEqual(("ruRU",), report.validated_locales)


if __name__ == "__main__":
    unittest.main()
