import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from automation.translate_locale import _generate, translate_locale


# Describe: isolated locale translation worker
class TranslateLocaleTests(unittest.TestCase):
    def test_reserves_time_for_validation_and_artifact_upload(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a locale generation running inside a 30-minute job
            root = Path(temporary_directory)
            terminology_path = root / "terminology.json"
            terminology_path.write_text("{}", encoding="utf-8")
            observed_timeout = 0

            def run(command, timeout_seconds=None):
                nonlocal observed_timeout
                observed_timeout = timeout_seconds
                output_path = Path(command[command.index("--output") + 1])
                output_path.write_text(
                    json.dumps({"retrievedAt": "now", "changes": []}),
                    encoding="utf-8",
                )
                return ""

            # When Gemini generation receives its subprocess budget
            with patch("automation.translate_locale._run", side_effect=run):
                _generate(
                    {"updatedAt": "now", "changes": []},
                    "deDE",
                    terminology_path,
                )

            # Then ten minutes remain for setup, validation, and upload
            self.assertEqual(1200, observed_timeout)

    def test_prepares_current_official_locale_before_agent_generation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given the translation stage can obtain a current official locale
            root = Path(temporary_directory)
            english_path = root / "english.json"
            terminology_path = root / "terminology.json"
            output_path = root / "result.json"
            document = {"updatedAt": "2026-08-20T04:07:00+00:00", "changes": []}
            english_path.write_text(json.dumps(document), encoding="utf-8")
            terminology_path.write_text("{}", encoding="utf-8")
            observed = {"prepared": False}

            def prepare(current, locale):
                observed["prepared"] = locale == "frFR"
                current["officialLocalePrepared"] = locale

            def generate(current, locale, _terminology):
                self.assertTrue(observed["prepared"])
                self.assertEqual(locale, current["officialLocalePrepared"])
                return {"retrievedAt": current["updatedAt"], "changes": []}

            # When the locale worker runs
            exit_code = translate_locale(
                locale="frFR",
                english_path=english_path,
                terminology_path=terminology_path,
                output_path=output_path,
                prepare_official=prepare,
                generate=generate,
                validate=lambda _batch, _locale, _terminology: (),
            )

            # Then official localization preparation precedes Gemini generation
            self.assertEqual(0, exit_code)
            self.assertTrue(observed["prepared"])

    def test_writes_a_pass_artifact_for_one_validated_locale(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given an English document and a successful locale translator
            root = Path(temporary_directory)
            english_path = root / "english.json"
            terminology_path = root / "terminology.json"
            output_path = root / "result.json"
            document = {"updatedAt": "2026-08-20T04:07:00+00:00", "changes": []}
            english_path.write_text(json.dumps(document), encoding="utf-8")
            terminology_path.write_text("{}", encoding="utf-8")
            translated = {"retrievedAt": document["updatedAt"], "changes": []}

            # When that locale is translated and validated
            exit_code = translate_locale(
                locale="deDE",
                english_path=english_path,
                terminology_path=terminology_path,
                output_path=output_path,
                prepare_official=lambda _document, _locale: None,
                generate=lambda _document, _locale, _terminology: translated,
                validate=lambda _batch, _locale, _terminology: (),
            )

            # Then a locale-specific passing artifact is retained
            self.assertEqual(0, exit_code)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("deDE", result["locale"])
            self.assertEqual("PASS", result["status"])
            self.assertEqual(translated, result["batch"])

    def test_allows_an_explicit_mexican_spanish_translation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given Mexican Spanish is optional for unattended releases
            root = Path(temporary_directory)
            english_path = root / "english.json"
            terminology_path = root / "terminology.json"
            output_path = root / "result.json"
            document = {
                "updatedAt": "2026-08-20T04:07:00+00:00",
                "changes": [],
            }
            english_path.write_text(json.dumps(document), encoding="utf-8")
            terminology_path.write_text("{}", encoding="utf-8")

            # When Mexican Spanish is explicitly requested
            exit_code = translate_locale(
                locale="esMX",
                english_path=english_path,
                terminology_path=terminology_path,
                output_path=output_path,
                prepare_official=lambda _document, _locale: None,
                generate=lambda current, _locale, _terminology: current,
                validate=lambda _batch, _locale, _terminology: (),
            )

            # Then the translation tooling accepts the optional locale
            self.assertEqual(0, exit_code)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("esMX", result["locale"])
            self.assertEqual("PASS", result["status"])

    def test_writes_a_failed_artifact_when_generation_times_out(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given generation exceeds its isolated process budget
            root = Path(temporary_directory)
            english_path = root / "english.json"
            terminology_path = root / "terminology.json"
            output_path = root / "result.json"
            english_path.write_text(
                json.dumps({"updatedAt": "2026-08-20T04:07:00+00:00", "changes": []}),
                encoding="utf-8",
            )
            terminology_path.write_text("{}", encoding="utf-8")

            def timeout(_document, _locale, _terminology):
                raise RuntimeError("translation generation exceeded 1500 seconds")

            # When the worker handles the failure
            exit_code = translate_locale(
                locale="ruRU",
                english_path=english_path,
                terminology_path=terminology_path,
                output_path=output_path,
                prepare_official=lambda _document, _locale: None,
                generate=timeout,
                validate=lambda _batch, _locale, _terminology: (),
            )

            # Then it fails closed and preserves a safe diagnostic artifact
            self.assertEqual(1, exit_code)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("FAILED", result["status"])
            self.assertIn("exceeded 1500 seconds", result["reason"])
            self.assertNotIn("batch", result)

    def test_preserves_generated_batch_when_validation_fails(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given generation succeeds but validation rejects the translation
            root = Path(temporary_directory)
            english_path = root / "english.json"
            terminology_path = root / "terminology.json"
            output_path = root / "result.json"
            document = {
                "updatedAt": "2026-08-20T04:07:00+00:00",
                "changes": [],
            }
            english_path.write_text(json.dumps(document), encoding="utf-8")
            terminology_path.write_text("{}", encoding="utf-8")
            translated = {
                "retrievedAt": document["updatedAt"],
                "changes": [],
            }

            def reject(_batch, _locale, _terminology):
                raise ValueError("bullet 1 loses condition")

            # When the worker records the validation failure
            exit_code = translate_locale(
                locale="esES",
                english_path=english_path,
                terminology_path=terminology_path,
                output_path=output_path,
                prepare_official=lambda _document, _locale: None,
                generate=lambda _document, _locale, _terminology: translated,
                validate=reject,
            )

            # Then it remains failed but retains the candidate for manual repair
            self.assertEqual(1, exit_code)
            result = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual("FAILED", result["status"])
            self.assertEqual(translated, result["batch"])


if __name__ == "__main__":
    unittest.main()
