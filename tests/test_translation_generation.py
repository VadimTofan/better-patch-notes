import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "scripts"
    / "generate_translations.py"
)


def _load_generator_module():
    if not GENERATOR_PATH.exists():
        return None

    specification = importlib.util.spec_from_file_location(
        "generate_translations",
        GENERATOR_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load generate_translations.py")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)

    return module


# Describe: safe generation of unofficial patch-note localizations
class TranslationGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.generator = _load_generator_module()

    def test_loads_primary_and_fallback_gemini_keys_from_environment_and_file(
        self,
    ) -> None:
        # Given a process primary key and a file-based fallback key
        self.assertIsNotNone(self.generator)
        load_keys = getattr(self.generator, "load_gemini_api_keys", None)
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_path = Path(temporary_directory) / ".env"
            env_path.write_text(
                "GEMINI_API_KEY=file-primary\n"
                "GEMINI_API_KEY2=file-secondary\n",
                encoding="utf-8",
            )

            # When Gemini credentials are loaded
            self.assertTrue(callable(load_keys))
            keys = load_keys(
                env_path=env_path,
                environment={"GEMINI_API_KEY": "process-primary"},
            )

        # Then process values take precedence and the fallback remains usable
        self.assertEqual(
            ("process-primary", "file-secondary"),
            keys,
        )

    def test_uses_fallback_key_after_primary_authentication_failure(
        self,
    ) -> None:
        # Given a rejected primary key and a working fallback key
        self.assertIsNotNone(self.generator)
        translator_type = getattr(self.generator, "GeminiTranslator", None)
        error_type = getattr(self.generator, "GeminiApiError", None)
        attempted_keys: list[str] = []

        self.assertTrue(callable(translator_type))
        self.assertTrue(callable(error_type))

        def request_translation(
            api_key: str,
            _text: str,
            _language: str,
        ) -> str:
            attempted_keys.append(api_key)
            if api_key == "primary-secret":
                raise error_type(401, "authentication")
            return "Schaden erhöht"

        translator = translator_type(
            ("primary-secret", "fallback-secret"),
            request_translation=request_translation,
            sleep=lambda _seconds: None,
        )

        # When translation is requested
        translated = translator("damage increased", "de")

        # Then the failed key is skipped and the fallback result is returned
        self.assertEqual("Schaden erhöht", translated)
        self.assertEqual(
            ["primary-secret", "fallback-secret"],
            attempted_keys,
        )

    def test_stops_without_exposing_credentials_when_both_keys_fail(
        self,
    ) -> None:
        # Given two Gemini keys that are both rejected
        self.assertIsNotNone(self.generator)

        def request_translation(
            _api_key: str,
            _text: str,
            _language: str,
        ) -> str:
            raise self.generator.GeminiApiError(403, "permission_denied")

        translator = self.generator.GeminiTranslator(
            ("primary-secret", "fallback-secret"),
            request_translation=request_translation,
            sleep=lambda _seconds: None,
        )

        # When translation is attempted
        with self.assertRaises(RuntimeError) as raised:
            translator("damage increased", "de")

        # Then the run stops without placing either credential in the error
        message = str(raised.exception)
        self.assertIn("translation stopped", message)
        self.assertIn("403", message)
        self.assertNotIn("primary-secret", message)
        self.assertNotIn("fallback-secret", message)

    def test_retries_transient_failures_before_using_fallback_key(self) -> None:
        # Given a primary key with repeated transient failures and a fallback
        self.assertIsNotNone(self.generator)
        attempted_keys: list[str] = []
        sleep_durations: list[float] = []

        def request_translation(
            api_key: str,
            _text: str,
            _language: str,
        ) -> str:
            attempted_keys.append(api_key)
            if api_key == "primary-secret":
                raise self.generator.GeminiApiError(429, "resource_exhausted")
            return "Schaden erhöht"

        translator = self.generator.GeminiTranslator(
            ("primary-secret", "fallback-secret"),
            request_translation=request_translation,
            sleep=sleep_durations.append,
        )

        # When translation is requested
        translated = translator("damage increased", "de")

        # Then retries are bounded before the fallback key is selected
        self.assertEqual("Schaden erhöht", translated)
        self.assertEqual(
            [
                "primary-secret",
                "primary-secret",
                "primary-secret",
                "primary-secret",
                "fallback-secret",
            ],
            attempted_keys,
        )
        self.assertEqual([1, 2, 4], sleep_durations)

    def test_requests_translation_through_gemini_interactions_api(self) -> None:
        # Given a successful Gemini Interactions API response
        self.assertIsNotNone(self.generator)
        request_translation = getattr(
            self.generator,
            "request_gemini_translation",
            None,
        )
        captured_requests = []

        class FakeRateLimiter:
            def __init__(self) -> None:
                self.wait_count = 0

            def wait(self) -> None:
                self.wait_count += 1

        rate_limiter = FakeRateLimiter()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, _exception_type, _exception, _traceback):
                return False

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "status": "completed",
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "Schaden erhöht",
                                    }
                                ],
                            }
                        ],
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):
            captured_requests.append((request, timeout))
            return FakeResponse()

        # When a translation is requested
        self.assertTrue(callable(request_translation))
        with (
            patch.object(self.generator, "urlopen", fake_urlopen),
            patch.object(
                self.generator,
                "GEMINI_REQUEST_LIMITER",
                rate_limiter,
            ),
        ):
            translated = request_translation(
                "test-api-key",
                "damage from __BPN0000__ increased",
                "de",
            )

        # Then the authenticated Gemini endpoint receives a constrained prompt
        self.assertEqual("Schaden erhöht", translated)
        self.assertEqual(1, len(captured_requests))
        request, timeout = captured_requests[0]
        request_body = json.loads(request.data.decode("utf-8"))
        headers = dict(request.header_items())

        self.assertEqual(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            request.full_url,
        )
        self.assertEqual(30, timeout)
        self.assertEqual("test-api-key", headers["X-goog-api-key"])
        self.assertEqual("gemini-3.5-flash-lite", request_body["model"])
        self.assertIn("German", request_body["input"])
        self.assertIn(
            "damage from __BPN0000__ increased",
            request_body["input"],
        )
        self.assertIn(
            "Required placeholders: __BPN0000__",
            request_body["input"],
        )
        self.assertIn(
            "Do not add numeric literals",
            request_body["input"],
        )
        self.assertEqual(1, rate_limiter.wait_count)

    def test_limits_translation_request_starts_to_five_per_minute(self) -> None:
        # Given a limiter configured for five request starts per minute
        self.assertIsNotNone(self.generator)
        current_time = [100.0]
        sleep_durations: list[float] = []

        def monotonic() -> float:
            return current_time[0]

        def sleep(seconds: float) -> None:
            sleep_durations.append(seconds)
            current_time[0] += seconds

        limiter = self.generator.GeminiRequestRateLimiter(
            requests_per_minute=5,
            monotonic=monotonic,
            sleep=sleep,
        )

        # When three request starts are admitted
        limiter.wait()
        limiter.wait()
        limiter.wait()

        # Then starts are spaced twelve seconds apart
        self.assertEqual([12.0, 12.0], sleep_durations)

    def test_rate_limits_batch_submission(self) -> None:
        # Given one Batch API submission and a shared request limiter
        self.assertIsNotNone(self.generator)

        class FakeRateLimiter:
            def __init__(self) -> None:
                self.wait_count = 0

            def wait(self) -> None:
                self.wait_count += 1

        rate_limiter = FakeRateLimiter()

        # When the batch request is submitted
        with (
            patch.object(
                self.generator,
                "GEMINI_REQUEST_LIMITER",
                rate_limiter,
            ),
            patch.object(
                self.generator,
                "_open_json_request",
                return_value={"name": "batches/123"},
            ),
        ):
            job_name, _api_key = self.generator.submit_inline_batch(
                ("test-key",),
                [],
            )

        # Then the shared limiter gates the request start
        self.assertEqual("batches/123", job_name)
        self.assertEqual(1, rate_limiter.wait_count)

    def test_uses_flash_lite_for_high_volume_translation_batches(self) -> None:
        # Given a high-volume batch request
        self.assertIsNotNone(self.generator)
        captured_options: dict[str, object] = {}

        def fake_request_output(
            _api_key: str,
            _prompt: str,
            timeout: int = 30,
            model: str | None = None,
        ) -> str:
            captured_options["prompt"] = _prompt
            captured_options["timeout"] = timeout
            captured_options["model"] = model
            return '["Schaden erhöht"]'

        # When the Gemini batch transport is selected
        with patch.object(
            self.generator,
            "_request_gemini_output",
            fake_request_output,
        ):
            response = self.generator.request_gemini_translation_batch(
                "test-api-key",
                '["damage increased"]',
                "de",
            )

        # Then the structured high-throughput model and batch timeout are used
        self.assertEqual('["Schaden erhöht"]', response)
        self.assertEqual(120, captured_options["timeout"])
        self.assertEqual(
            "gemini-3.5-flash-lite",
            captured_options["model"],
        )
        self.assertIn(
            "Do not add numeric literals",
            captured_options["prompt"],
        )

    def test_uses_distinct_language_prompts_for_spanish_regions(self) -> None:
        # Given the two supported regional Spanish locales
        self.assertIsNotNone(self.generator)

        # When their translation language codes and names are inspected
        spain_code = self.generator.TARGET_LANGUAGE_CODES["esES"]
        latin_america_code = self.generator.TARGET_LANGUAGE_CODES["esMX"]

        # Then each locale receives its own regional translation prompt
        self.assertEqual("es-ES", spain_code)
        self.assertEqual("es-MX", latin_america_code)
        self.assertEqual("Spanish (Spain)", self.generator.LANGUAGE_NAMES[spain_code])
        self.assertEqual(
            "Spanish (Latin America)",
            self.generator.LANGUAGE_NAMES[latin_america_code],
        )

    def test_preserves_wow_terms_while_translating_surrounding_prose(self) -> None:
        # Given a patch-note bullet containing ability and encounter names
        self.assertIsNotNone(self.generator)
        text = "Merektha – Toxic Viper: Increased health by 17.5%."

        def fake_translator(protected_text: str, _language: str) -> str:
            return protected_text.replace("Increased health by", "Vida aumentada em")

        # When the guarded translation is generated
        translated, uncertain_terms = self.generator.translate_guarded_text(
            text,
            "pt",
            fake_translator,
        )

        # Then WoW terms and numeric meaning remain intact
        self.assertEqual(
            "Merektha – Toxic Viper: Vida aumentada em 17.5%.",
            translated,
        )
        self.assertEqual(("Merektha", "Toxic Viper"), uncertain_terms)

    def test_translates_each_bullet_as_one_grammatical_request(self) -> None:
        # Given a sentence containing protected game terminology and a number
        self.assertIsNotNone(self.generator)
        translation_requests: list[str] = []

        def whole_bullet_translator(text: str, _language: str) -> str:
            translation_requests.append(text)
            return (
                "Der Schaden von __BPN0000__ wurde um "
                "__BPN0001__ erhöht."
            )

        # When guarded translation is performed
        translated, uncertain_terms = self.generator.translate_guarded_text(
            "Damage from Moonfire increased by 5%.",
            "de",
            whole_bullet_translator,
        )

        # Then one request retains the full grammatical sentence context
        self.assertEqual(1, len(translation_requests))
        self.assertIn("Damage from", translation_requests[0])
        self.assertIn("increased by", translation_requests[0])
        self.assertEqual(
            "Der Schaden von Moonfire wurde um 5% erhöht.",
            translated,
        )
        self.assertEqual(("Moonfire",), uncertain_terms)

    def test_translates_a_locale_batch_in_one_ordered_request(self) -> None:
        # Given three protected bullets for one locale
        self.assertIsNotNone(self.generator)
        requests: list[tuple[str, str]] = []

        def batch_translator(text: str, language: str) -> str:
            requests.append((text, language))
            source = json.loads(text)
            return json.dumps([f"de: {item}" for item in source])

        # When the locale batch is translated
        translated = self.generator.translate_text_batch(
            ("first", "second", "third"),
            "de",
            batch_translator,
        )

        # Then one request returns the same number of ordered translations
        self.assertEqual(
            ("de: first", "de: second", "de: third"),
            translated,
        )
        self.assertEqual(1, len(requests))
        self.assertEqual("de", requests[0][1])

    def test_chunks_large_locale_batches_without_reordering(self) -> None:
        # Given five protected bullets and a two-item request limit
        self.assertIsNotNone(self.generator)
        request_sizes: list[int] = []

        def batch_translator(text: str, _language: str) -> str:
            source = json.loads(text)
            request_sizes.append(len(source))
            return json.dumps([f"translated: {item}" for item in source])

        # When the locale batch is translated in bounded chunks
        translated = self.generator.translate_text_batch(
            ("one", "two", "three", "four", "five"),
            "de",
            batch_translator,
            batch_size=2,
        )

        # Then every item remains ordered across the three requests
        self.assertEqual([2, 2, 1], request_sizes)
        self.assertEqual(
            (
                "translated: one",
                "translated: two",
                "translated: three",
                "translated: four",
                "translated: five",
            ),
            translated,
        )

    def test_repairs_a_chunk_item_that_drops_a_protected_placeholder(
        self,
    ) -> None:
        # Given a chunk response that omits one protected WoW term
        self.assertIsNotNone(self.generator)
        batch_requests: list[list[str]] = []
        repair_requests: list[str] = []

        def batch_translator(text: str, _language: str) -> str:
            source = json.loads(text)
            batch_requests.append(source)
            return json.dumps(
                ["de: __BPN0000__", "de: missing term"]
            )

        def repair_translator(text: str, _language: str) -> str:
            repair_requests.append(text)
            return "de: __BPN0000__ repaired"

        # When the locale chunk is translated
        translated = self.generator.translate_text_batch(
            ("first __BPN0000__", "second __BPN0000__"),
            "de",
            batch_translator,
            repair_translator=repair_translator,
        )

        # Then only the invalid item is retried as a complete bullet
        self.assertEqual(
            ("de: __BPN0000__", "de: __BPN0000__ repaired"),
            translated,
        )
        self.assertEqual(
            [["first __BPN0000__", "second __BPN0000__"]],
            batch_requests,
        )
        self.assertEqual(["second __BPN0000__"], repair_requests)

    def test_normalizes_placeholder_case_without_an_extra_request(self) -> None:
        # Given Gemini changes only the capitalization of a placeholder
        self.assertIsNotNone(self.generator)
        request_count = 0

        def batch_translator(_text: str, _language: str) -> str:
            nonlocal request_count
            request_count += 1
            return json.dumps(["de: __Bpn0000__"])

        # When the translated chunk is validated
        translated = self.generator.translate_text_batch(
            ("first __BPN0000__",),
            "de",
            batch_translator,
        )

        # Then the internal marker is restored to its canonical form
        self.assertEqual(("de: __BPN0000__",), translated)
        self.assertEqual(1, request_count)

    def test_repairs_a_chunk_item_that_introduces_a_numeric_literal(
        self,
    ) -> None:
        # Given Gemini adds a digit that was not present outside placeholders
        self.assertIsNotNone(self.generator)
        repair_requests: list[str] = []

        def batch_translator(_text: str, _language: str) -> str:
            return json.dumps(["de: __BPN0000__ target 2"])

        def repair_translator(text: str, _language: str) -> str:
            repair_requests.append(text)
            return "de: __BPN0000__ target"

        # When the translated item is validated
        translated = self.generator.translate_text_batch(
            ("de: __BPN0000__ target",),
            "de",
            batch_translator,
            repair_translator=repair_translator,
        )

        # Then it is repaired without the invented number
        self.assertEqual(("de: __BPN0000__ target",), translated)
        self.assertEqual(["de: __BPN0000__ target"], repair_requests)

    def test_retries_a_malformed_placeholder_repair_within_the_bound(self) -> None:
        # Given
        self.assertIsNotNone(self.generator)
        repair_requests: list[str] = []

        def batch_translator(_text: str, _language: str) -> str:
            return json.dumps(["de: placeholder missing"])

        def repair_translator(text: str, _language: str) -> str:
            repair_requests.append(text)
            if len(repair_requests) < 3:
                return "de: placeholder still missing"
            return "de: __BPN0000__ repaired"

        # When
        translated = self.generator.translate_text_batch(
            ("source __BPN0000__",),
            "de",
            batch_translator,
            repair_translator=repair_translator,
        )

        # Then
        self.assertEqual(("de: __BPN0000__ repaired",), translated)
        self.assertEqual(3, len(repair_requests))

    def test_reports_locale_and_item_when_placeholder_repairs_fail(self) -> None:
        # Given a batch and every bounded repair omit the protected marker
        self.assertIsNotNone(self.generator)
        repair_requests: list[str] = []

        def batch_translator(_text: str, _language: str) -> str:
            return json.dumps(["de: placeholder missing"])

        def repair_translator(text: str, _language: str) -> str:
            repair_requests.append(text)
            return "de: placeholder still missing"

        # When the invalid translation exhausts all repair attempts
        with self.assertRaisesRegex(
            RuntimeError,
            r"locale de, item 1",
        ):
            self.generator.translate_text_batch(
                ("source __BPN0000__",),
                "de",
                batch_translator,
                repair_translator=repair_translator,
            )

        # Then retries remain bounded and no source text appears in the error
        self.assertEqual(3, len(repair_requests))

    def test_builds_and_parses_keyed_batch_api_requests(self) -> None:
        # Given two protected bullets for two target languages
        self.assertIsNotNone(self.generator)
        protected_texts = ("first __BPN0000__", "second __BPN0000__")

        # When an inline Batch API payload is built
        requests = self.generator.build_inline_batch_requests(
            protected_texts,
            {"de": "German", "fr": "French"},
        )

        # Then every request has a stable key and whole-bullet prompt
        self.assertEqual(4, len(requests))
        self.assertEqual("de:0", requests[0]["metadata"]["key"])
        first_prompt = requests[0]["request"]["contents"][0]["parts"][0][
            "text"
        ]
        self.assertIn("German", first_prompt)
        self.assertIn("first __BPN0000__", first_prompt)

        response = {
            "state": "JOB_STATE_SUCCEEDED",
            "dest": {
                "inlinedResponses": [
                    {
                        "metadata": {"key": request["metadata"]["key"]},
                        "response": {
                            "candidates": [
                                {
                                    "content": {
                                        "parts": [
                                            {
                                                "text": (
                                                    "translated "
                                                    + request["metadata"]["key"]
                                                )
                                            }
                                        ]
                                    }
                                }
                            ]
                        },
                    }
                    for request in requests
                ]
            },
        }

        # When successful results are parsed
        translations = self.generator.parse_inline_batch_results(
            response,
            expected_keys=tuple(
                request["metadata"]["key"] for request in requests
            ),
        )

        # Then results are aligned by metadata rather than response position
        self.assertEqual("translated de:0", translations["de:0"])
        self.assertEqual("translated fr:1", translations["fr:1"])

    def test_uses_interactive_translation_when_batch_requires_paid_tier(
        self,
    ) -> None:
        # Given a working key whose project cannot use the paid Batch API
        self.assertIsNotNone(self.generator)
        requested_languages: list[str] = []

        def unavailable_batch(_api_keys, _requests):
            raise self.generator.GeminiApiError(
                400,
                "failed_precondition",
            )

        def interactive_batch(_api_key, serialized_texts, language):
            requested_languages.append(language)
            source_texts = json.loads(serialized_texts)
            return json.dumps(
                [f"{language}: {text}" for text in source_texts]
            )

        # When protected texts are translated for two locales
        with (
            patch.object(
                self.generator,
                "submit_inline_batch",
                unavailable_batch,
            ),
            patch.object(
                self.generator,
                "request_gemini_translation_batch",
                interactive_batch,
            ),
        ):
            translations, transport = (
                self.generator.generate_protected_translations(
                    ("test-key",),
                    ("first", "second"),
                    {"de": "German", "fr": "French"},
                )
            )

        # Then normal requests provide complete, keyed fallback results
        self.assertEqual("interactive", transport)
        self.assertEqual(["de", "fr"], requested_languages)
        self.assertEqual("de: first", translations[("de", "first")])
        self.assertEqual("fr: second", translations[("fr", "second")])

    def test_interactive_failure_is_isolated_to_one_locale(self) -> None:
        # Given German drops a protected term while French preserves it
        self.assertIsNotNone(self.generator)

        def unavailable_batch(_api_keys, _requests):
            raise self.generator.GeminiApiError(
                400,
                "failed_precondition",
            )

        def interactive_batch(_api_key, serialized_texts, language):
            source_texts = json.loads(serialized_texts)
            if language == "de":
                return json.dumps(["de: placeholder missing"])
            return json.dumps(
                [f"{language}: {text}" for text in source_texts]
            )

        def interactive_repair(_api_key, _text, language):
            if language == "de":
                return "de: placeholder still missing"
            return "fr: __BPN0000__"

        # When the interactive fallback translates both locales
        with (
            patch.object(
                self.generator,
                "submit_inline_batch",
                unavailable_batch,
            ),
            patch.object(
                self.generator,
                "request_gemini_translation_batch",
                interactive_batch,
            ),
            patch.object(
                self.generator,
                "request_gemini_translation",
                interactive_repair,
            ),
        ):
            translations, transport = (
                self.generator.generate_protected_translations(
                    ("test-key",),
                    ("source __BPN0000__",),
                    {"de": "German", "fr": "French"},
                )
            )

        # Then French remains publishable and only German is a fallback
        self.assertEqual("interactive", transport)
        self.assertNotIn(("de", "source __BPN0000__"), translations)
        self.assertEqual(
            "fr: source __BPN0000__",
            translations[("fr", "source __BPN0000__")],
        )

    def test_failed_language_becomes_only_its_locale_fallback(self) -> None:
        # Given French succeeded while German produced no translations
        self.assertIsNotNone(self.generator)
        translations = {
            ("fr", "source __BPN0000__"): "fr: source __BPN0000__",
        }

        # When translation results are mapped back to WoW locales
        successful, fallback_reasons = (
            self.generator.classify_locale_outcomes(
                translations,
                {"deDE": "de", "frFR": "fr"},
            )
        )

        # Then only the failed locale receives an English fallback
        self.assertEqual({"frFR": "fr"}, successful)
        self.assertEqual(
            {"deDE": "automatic translation generation failed"},
            fallback_reasons,
        )

    def test_uses_interactive_translation_when_batch_wait_times_out(
        self,
    ) -> None:
        # Given Gemini accepts a batch job that remains queued past the deadline
        self.assertIsNotNone(self.generator)
        requested_languages: list[str] = []

        def interactive_batch(_api_key, serialized_texts, language):
            requested_languages.append(language)
            source_texts = json.loads(serialized_texts)
            return json.dumps(
                [f"{language}: {text}" for text in source_texts]
            )

        # When the bounded batch wait expires
        with (
            patch.object(
                self.generator,
                "submit_inline_batch",
                return_value=("batches/queued", "test-key"),
            ),
            patch.object(
                self.generator,
                "wait_for_inline_batch",
                side_effect=self.generator.GeminiBatchTimeoutError(
                    "Gemini batch timed out."
                ),
            ),
            patch.object(
                self.generator,
                "request_gemini_translation_batch",
                interactive_batch,
            ),
        ):
            translations, transport = (
                self.generator.generate_protected_translations(
                    ("test-key",),
                    ("first", "second"),
                    {"de": "German", "fr": "French"},
                )
            )

        # Then the existing rate-limited interactive transport completes it
        self.assertEqual("interactive", transport)
        self.assertEqual(["de", "fr"], requested_languages)
        self.assertEqual("de: first", translations[("de", "first")])
        self.assertEqual("fr: second", translations[("fr", "second")])

    def test_batch_polling_stops_at_its_deadline(self) -> None:
        # Given Gemini keeps an accepted batch job in a queued state
        self.assertIsNotNone(self.generator)
        clock = iter((0.0, 0.0, 10.0))
        sleeps: list[float] = []

        # When polling reaches the configured deadline
        with patch.object(
            self.generator,
            "_open_json_request",
            return_value={"state": "JOB_STATE_QUEUED"},
        ):
            with self.assertRaisesRegex(
                self.generator.GeminiBatchTimeoutError,
                "10 seconds",
            ):
                self.generator.wait_for_inline_batch(
                    "batches/queued",
                    "test-key",
                    poll_interval=30,
                    timeout_seconds=10,
                    monotonic=lambda: next(clock),
                    sleep=sleeps.append,
                )

        # Then it sleeps only to the deadline and does not poll forever
        self.assertEqual([10.0], sleeps)

    def test_builds_every_requested_locale_without_changing_bullet_count(self) -> None:
        # Given one canonical English record and two target locales
        self.assertIsNotNone(self.generator)
        source_url = "https://news.blizzard.com/en-us/example"
        document = {
            "schemaVersion": 5,
            "updatedAt": "2026-08-02T18:00:00+02:00",
            "changes": [
                {
                    "channel": "ptr",
                    "category": "Class",
                    "date": "2026-08-02",
                    "patch": "12.1",
                    "localizations": {
                        "en": {
                            "name": "Mage",
                            "specialization": "Fire",
                            "change": ["All damage increased by 6%."],
                            "source": "Blizzard",
                            "sourceUrl": source_url,
                            "translationType": "official",
                            "translatedFrom": "",
                            "terminologySourceUrls": [],
                        }
                    },
                }
            ],
        }

        def fake_translator(text: str, language: str) -> str:
            return f"{language}: {text}"

        # When translations are generated
        batch = self.generator.build_translation_batch(
            document,
            {"deDE": "de", "frFR": "fr"},
            fake_translator,
        )

        # Then each locale is present and remains aligned with English
        self.assertIn("retrievedAt", batch)
        self.assertEqual(
            "2026-08-02T18:00:00+02:00",
            batch["retrievedAt"],
        )
        self.assertEqual("", batch["changes"][0]["replacesSourceUrl"])
        self.assertNotIn("id", batch["changes"][0])
        localizations = batch["changes"][0]["localizations"]
        self.assertEqual({"en", "deDE", "frFR"}, set(localizations))
        self.assertEqual(1, len(localizations["deDE"]["change"]))
        self.assertEqual("agent", localizations["frFR"]["translationType"])
        self.assertEqual("en", localizations["frFR"]["translatedFrom"])

    def test_keeps_protected_content_out_of_chinese_translation(self) -> None:
        # Given a WoW term that must survive Simplified Chinese translation
        self.assertIsNotNone(self.generator)

        def chinese_translator(segment: str, _language: str) -> str:
            self.assertIn("__BPN0000__", segment)
            self.assertIn("__BPN0001__", segment)
            self.assertNotIn("Moonfire", segment)
            self.assertNotIn("5%", segment)
            return segment.replace("damage increased", "伤害提高")

        # When the guarded translation is generated
        translated, _uncertain_terms = self.generator.translate_guarded_text(
            "Moonfire damage increased by 5%.",
            "zh-CN",
            chinese_translator,
        )

        # Then the protected ability name is restored exactly
        self.assertEqual("Moonfire 伤害提高 by 5%.", translated)

    def test_keeps_numeric_tokens_out_of_translation(self) -> None:
        # Given a tier-set number that a translator could spell out
        self.assertIsNotNone(self.generator)
        text = "Midnight Season 1 2-set bonus increased by 3% (was 5%)."

        def fake_translator(segment: str, _language: str) -> str:
            self.assertNotIn("Season 1", segment)
            self.assertNotIn("2-set", segment)
            self.assertNotIn("3%", segment)
            self.assertNotIn("5%", segment)
            self.assertIn("__BPN", segment)
            return segment.replace("bonus increased", "bonus erhöht")

        # When guarded translation runs
        translated, _uncertain_terms = self.generator.translate_guarded_text(
            text,
            "de",
            fake_translator,
        )

        # Then every literal numeric token is restored unchanged
        self.assertEqual(
            "Midnight Season 1 2-set bonus erhöht by 3% (was 5%).",
            translated,
        )

    def test_never_sends_protected_content_to_the_translator(self) -> None:
        # Given a bullet containing both a WoW ability and numeric values
        self.assertIsNotNone(self.generator)
        translated_segments: list[str] = []

        def inspecting_translator(segment: str, _language: str) -> str:
            translated_segments.append(segment)
            self.assertNotIn("Moonfire", segment)
            self.assertNotIn("5%", segment)
            self.assertIn("__BPN0000__", segment)
            self.assertIn("__BPN0001__", segment)
            return segment.replace("damage increased by", "Schaden erhöht um")

        # When segmented translation is performed
        translated, uncertain_terms = self.generator.translate_guarded_text(
            "Moonfire damage increased by 5%.",
            "de",
            inspecting_translator,
        )

        # Then protected values bypass translation and are restored verbatim
        self.assertEqual("Moonfire Schaden erhöht um 5%.", translated)
        self.assertEqual(("Moonfire",), uncertain_terms)
        self.assertGreater(len(translated_segments), 0)

    def test_preserves_spacing_when_translation_trims_fragments(self) -> None:
        # Given a service that trims spaces around translated fragments
        self.assertIsNotNone(self.generator)

        def trimming_translator(segment: str, _language: str) -> str:
            return segment.strip().replace(
                "damage increased by",
                "Schaden erhöht um",
            )

        # When protected terms and numbers split the sentence
        translated, _uncertain_terms = self.generator.translate_guarded_text(
            "Moonfire damage increased by 5%.",
            "de",
            trimming_translator,
        )

        # Then original boundary spacing is retained around protected content
        self.assertEqual("Moonfire Schaden erhöht um 5%.", translated)

    def test_restores_space_before_protected_term_in_russian(self) -> None:
        # Given a Russian translation joined directly to a protected WoW term
        self.assertIsNotNone(self.generator)

        def joined_translator(segment: str, _language: str) -> str:
            self.assertIn("__BPN0000__", segment)
            self.assertIn("__BPN0001__", segment)
            return "Урон__BPN0000__ увеличен на __BPN0001__."

        # When the protected English term is restored
        translated, _uncertain_terms = self.generator.translate_guarded_text(
            "Arcane Blast damage increased by 20%.",
            "ru",
            joined_translator,
        )

        # Then the Russian text and protected term remain word-separated
        self.assertNotIn("УронArcane", translated)
        self.assertIn("Урон Arcane Blast", translated)

    def test_keeps_chinese_protected_term_boundaries_unspaced(self) -> None:
        # Given Chinese text that conventionally touches a protected Latin term
        self.assertIsNotNone(self.generator)

        def joined_translator(segment: str, _language: str) -> str:
            self.assertIn("__BPN0000__", segment)
            self.assertIn("__BPN0001__", segment)
            return "__BPN0000__伤害提高了__BPN0001__。"

        # When the protected English term is restored
        translated, _uncertain_terms = self.generator.translate_guarded_text(
            "Arcane Blast damage increased by 20%.",
            "zh-CN",
            joined_translator,
        )

        # Then Chinese typography is not forced into space-delimited wording
        self.assertEqual("Arcane Blast伤害提高了20%。", translated)

    def test_protects_longer_overlapping_wow_terms_first(self) -> None:
        # Given a multi-word WoW term sharing a word with another term
        self.assertIsNotNone(self.generator)

        def fake_translator(segment: str, _language: str) -> str:
            return segment.replace("Beast", "Biest")

        # When guarded translation identifies overlapping names
        translated, uncertain_terms = self.generator.translate_guarded_text(
            "Blood is Life increases Blood Beast damage by 5%.",
            "de",
            fake_translator,
        )

        # Then the complete multi-word game term remains unchanged
        self.assertIn("Blood Beast", translated)
        self.assertNotIn("Blood Biest", translated)
        self.assertIn("Blood Beast", uncertain_terms)

    def test_protects_wow_terms_with_lowercase_connectors_as_one_term(
        self,
    ) -> None:
        # Given an ability name containing the lowercase connector "is"
        self.assertIsNotNone(self.generator)

        # When candidate terms are identified
        _protected, _replacements, terms = self.generator._protect_text(
            "San’layn: Blood is Life now accumulates damage."
        )

        # Then the complete ability name is protected as one uncertain term
        self.assertIn("Blood is Life", terms)
        self.assertNotIn("Blood", terms)
        self.assertNotIn("Life", terms)

    def test_does_not_classify_sentence_words_as_wow_terms(self) -> None:
        # Given capitalized prose that is not game terminology
        self.assertIsNotNone(self.generator)

        # When candidate terms are identified
        _protected, _replacements, terms = self.generator._protect_text(
            "If no target is selected, Chance to trigger is reduced."
        )

        # Then ordinary sentence words remain translatable
        self.assertNotIn("If", terms)
        self.assertNotIn("Chance", terms)

    def test_does_not_protect_change_direction_as_part_of_a_wow_term(
        self,
    ) -> None:
        # Given an encounter name follows an uppercase direction word
        self.assertIsNotNone(self.generator)

        # When candidate terms are identified
        _protected, _replacements, terms = self.generator._protect_text(
            "Burrow: Reduced Merektha’s movement speed by 10%."
        )

        # Then only the encounter term is protected and direction can translate
        self.assertIn("Merektha’s", terms)
        self.assertFalse(any(term.startswith("Reduced") for term in terms))

    def test_does_not_protect_physical_change_direction_prose(self) -> None:
        # Given a capitalized damage school follows an increase direction
        self.assertIsNotNone(self.generator)

        # When candidate terms are identified
        _protected, _replacements, terms = self.generator._protect_text(
            "Corruption: Increased Physical damage vulnerability to 300%."
        )

        # Then the complete semantic phrase remains translatable
        self.assertNotIn("Increased Physical", terms)
        self.assertNotIn("Physical", terms)

    def test_does_not_protect_sentence_pronouns(self) -> None:
        # Given ordinary capitalized pronouns begin sentences
        self.assertIsNotNone(self.generator)

        # When candidate terms are identified
        _protected, _replacements, terms = self.generator._protect_text(
            "We adjusted the talent. They now decrease damage taken."
        )

        # Then ordinary prose remains available to the translator
        self.assertNotIn("We", terms)
        self.assertNotIn("They", terms)

    def test_does_not_protect_developer_note_prose_as_wow_terms(self) -> None:
        # Given a developer note with ordinary prose before a class name
        self.assertIsNotNone(self.generator)

        # When candidate terms are identified
        _protected, _replacements, terms = self.generator._protect_text(
            "Developers’ notes: We’re slightly reducing Arms Warrior’s "
            "single-target damage."
        )

        # Then prose stays translatable while the class term stays protected
        self.assertNotIn("Developers’ notes", terms)
        self.assertFalse(
            any(term.startswith("Developers") for term in terms)
        )
        self.assertNotIn("We’re", terms)
        self.assertIn("Arms Warrior’s", terms)

    def test_does_not_protect_prose_in_the_feral_developer_note(self) -> None:
        # Given the developer note that caused the automatic German failure
        self.assertIsNotNone(self.generator)
        text = (
            "Developers' notes: Feral updates in Curse of Ula'tek are "
            "aimed at talent diversity. We'd like Chomp to be stronger. "
            "Additionally, Feral struggles in AOE. Much of its damage comes "
            "from Rampant Ferocity. To make it easier, move it to Gate 1."
        )

        # When candidate terms and numeric values are protected
        _protected, replacements, terms = self.generator._protect_text(text)

        # Then prose stays translatable while WoW terms and numbers remain safe
        for prose_term in (
            "Developers' notes",
            "notes",
            "We'd",
            "Additionally",
            "Much",
            "To",
        ):
            self.assertNotIn(prose_term, terms)
        for wow_term in (
            "Feral",
            "Curse of Ula'tek",
            "Chomp",
            "AOE",
            "Rampant Ferocity",
            "Gate",
        ):
            self.assertIn(wow_term, terms)
        protected_originals = {
            original for _placeholder, original in replacements
        }
        self.assertIn("1", protected_originals)

    def test_protects_number_words_that_locales_may_render_as_digits(self) -> None:
        # Given an ordinal word Korean commonly renders with a numeral
        self.assertIsNotNone(self.generator)

        def korean_translator(segment: str, _language: str) -> str:
            return segment.replace("secondary", "2차")

        # When guarded translation runs
        translated, _uncertain_terms = self.generator.translate_guarded_text(
            "Damage increased and secondary damage increased by 30%.",
            "ko",
            korean_translator,
        )

        # Then the translation cannot introduce a new numeric token
        self.assertIn("secondary", translated)
        self.assertNotIn("2차", translated)


if __name__ == "__main__":
    unittest.main()
