from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


from automation.models import HttpResponse, RegisteredSource, SourceRegistry
from automation.runner import (
    _run,
    _translator,
    _validator,
    build_runtime_terminology,
    collect_official_changes,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "blizzard"


class _FixtureClient:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self.responses = responses

    def get(self, url: str) -> HttpResponse:
        body = self.responses[url]
        mime_type = "application/json" if url.endswith("warcraft") else "text/html"
        if "versions" in url:
            mime_type = "text/plain"

        return HttpResponse(
            body=body,
            final_url=url,
            mime_type=mime_type,
            status=200,
            content_hash=sha256(body).hexdigest(),
        )


# Describe: end-to-end collection from allowlisted Blizzard responses
class AutomationRunnerTests(unittest.TestCase):
    def test_loads_documented_fallback_reasons_from_validation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given the validation process classifies one locale as fallback
            root = Path(temporary_directory)
            terminology_path = root / "terminology.json"
            terminology_path.write_text("{}", encoding="utf-8")
            output = json.dumps(
                {
                    "validated_locales": ["deDE"],
                    "fallback_locales": ["ruRU"],
                    "fallback_reasons": {
                        "ruRU": "automatic semantic validation failed",
                    },
                    "uncertain_terms": [],
                }
            )

            # When the runner loads the validator report
            with patch("automation.runner._run", return_value=output):
                report = _validator({"changes": []}, terminology_path)

            # Then the coordinator receives the exact documented reason
            self.assertEqual(
                {
                    "ruRU": "automatic semantic validation failed",
                },
                report.fallback_reasons,
            )

    def test_preserves_the_generated_batch_for_private_auditing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given the translation child process produces a complete batch
            root = Path(temporary_directory)
            terminology_path = root / "terminology.json"
            terminology_path.write_text("{}", encoding="utf-8")
            audit_path = root / "translation-batch.json"
            expected_batch = {
                "retrievedAt": "2026-08-06T04:07:00+02:00",
                "changes": [{"category": "Dungeon"}],
            }

            def write_translation(command: list[str]) -> str:
                output_index = command.index("--output") + 1
                output_path = Path(command[output_index])
                output_path.write_text(
                    json.dumps(expected_batch),
                    encoding="utf-8",
                )
                return ""

            # When the generated batch is loaded for coordination
            with (
                patch(
                    "automation.runner._run",
                    side_effect=write_translation,
                ),
                patch("automation.runner.WORK_DIRECTORY", root),
            ):
                actual_batch = _translator(
                    {"updatedAt": "2026-08-06T04:07:00+02:00"},
                    terminology_path,
                )

            # Then an aligned private diagnostic copy remains in .bpn-work
            self.assertEqual(expected_batch, actual_batch)
            self.assertTrue(audit_path.exists())
            self.assertEqual(
                expected_batch,
                json.loads(audit_path.read_text(encoding="utf-8")),
            )

    def test_translation_failure_returns_an_english_only_batch(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given automatic generation fails before producing an output file
            root = Path(temporary_directory)
            terminology_path = root / "terminology.json"
            terminology_path.write_text("{}", encoding="utf-8")
            document = {
                "updatedAt": "2026-08-06T04:07:00+02:00",
                "changes": [
                    {
                        "channel": "live",
                        "category": "Class",
                        "date": "2026-08-06",
                        "patch": "12.0.7",
                        "localizations": {
                            "en": {
                                "name": "Mage",
                                "specialization": "Arcane",
                                "change": ["Damage increased by 5%."],
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

            # When translation generation fails safely
            with (
                patch(
                    "automation.runner._run",
                    side_effect=RuntimeError("placeholder repair failed"),
                ),
                patch("automation.runner.WORK_DIRECTORY", root),
            ):
                batch = _translator(document, terminology_path)

            # Then English remains publishable and every locale can fall back
            self.assertEqual(document["updatedAt"], batch["retrievedAt"])
            change = batch["changes"][0]
            self.assertEqual({"en"}, set(change["localizations"]))
            self.assertEqual("", change["replacesSourceUrl"])
            self.assertEqual(
                batch,
                json.loads(
                    (root / "translation-batch.json").read_text(
                        encoding="utf-8"
                    )
                ),
            )

    def test_child_tools_are_forced_to_use_utf8_output(self) -> None:
        # Given
        completed = type(
            "Completed",
            (),
            {"returncode": 0, "stdout": "ok\n", "stderr": ""},
        )()

        # When
        with patch(
            "automation.runner.subprocess.run",
            return_value=completed,
        ) as run:
            output = _run(["python", "tool.py"])

        # Then
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment["PYTHONUTF8"], "1")
        self.assertEqual(environment["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(output, "ok")

    def test_reuses_validated_bundled_terms_for_automatic_translation(self) -> None:
        # Given
        base = {"schemaVersion": 1, "locales": {"ruRU": {"terms": {}}}}
        canonical = {
            "changes": [
                {
                    "localizations": {
                        "en": {"name": "Mage", "specialization": "Arcane"},
                        "ruRU": {
                            "name": "Маг",
                            "specialization": "Тайная магия",
                            "terminologySourceUrls": [
                                "https://worldofwarcraft.blizzard.com/ru-ru/game/classes/mage"
                            ],
                        },
                    }
                }
            ]
        }

        # When
        terminology = build_runtime_terminology(base, canonical)

        # Then
        terms = terminology["locales"]["ruRU"]["terms"]
        self.assertEqual(terms["Mage"]["localized"], "Маг")
        self.assertEqual(terms["Arcane"]["localized"], "Тайная магия")

    def test_rejects_conflicting_bundled_terminology(self) -> None:
        # Given
        base = {"schemaVersion": 1, "locales": {"ruRU": {"terms": {}}}}
        canonical = {
            "changes": [
                {
                    "localizations": {
                        "en": {"name": "Mage", "specialization": ""},
                        "ruRU": {
                            "name": "Маг",
                            "specialization": "",
                            "terminologySourceUrls": [
                                "https://worldofwarcraft.blizzard.com/ru-ru/game/classes/mage"
                            ],
                        },
                    }
                },
                {
                    "localizations": {
                        "en": {"name": "Mage", "specialization": ""},
                        "ruRU": {
                            "name": "Волшебник",
                            "specialization": "",
                            "terminologySourceUrls": [
                                "https://worldofwarcraft.blizzard.com/ru-ru/game/classes/mage"
                            ],
                        },
                    }
                },
            ]
        }

        # When / Then
        with self.assertRaisesRegex(ValueError, "conflicting terminology"):
            build_runtime_terminology(base, canonical)

    def test_collects_hydrated_and_qualified_live_changes(self) -> None:
        # Given
        news_url = "https://news.blizzard.com/en-us/api/news/world-of-warcraft"
        article_url = (
            "https://news.blizzard.com/en-us/article/24299999/"
            "hotfixes-august-4-2026"
        )
        version_urls = (
            "https://us.version.battle.net/wow/versions",
            "https://eu.version.battle.net/wow/versions",
        )
        sources = (
            RegisteredSource(
                url=news_url,
                kind="news_feed",
                channel="live",
                patch="current",
                locale="en",
                title_patterns=("hotfixes",),
            ),
            *(
                RegisteredSource(
                    url=url,
                    kind="version",
                    channel="live",
                    patch="current",
                    locale="en",
                    title_patterns=("wow",),
                )
                for url in version_urls
            ),
        )
        registry = SourceRegistry(
            allowed_hosts=frozenset(
                {"news.blizzard.com", "us.version.battle.net", "eu.version.battle.net"}
            ),
            blue_authors=frozenset({"Linxy"}),
            max_response_bytes=5_000_000,
            timeout_seconds=20,
            sources=sources,
        )
        version_body = (FIXTURE_ROOT / "product-versions.txt").read_bytes()
        client = _FixtureClient(
            {
                news_url: (FIXTURE_ROOT / "news-feed.json").read_bytes(),
                article_url: (FIXTURE_ROOT / "live-hotfix-notes.html").read_bytes(),
                version_urls[0]: version_body,
                version_urls[1]: version_body,
            }
        )

        # When
        current_patch, result, documents = collect_official_changes(
            registry=registry,
            client=client,
            as_of_date=date(2026, 8, 5),
        )

        # Then
        self.assertEqual(current_patch, "12.0.7")
        self.assertEqual(len(result.accepted), 3)
        self.assertEqual(len(documents), 1)
        self.assertIn("<h2>Hotfixes</h2>", documents[0].body.decode())


if __name__ == "__main__":
    unittest.main()
