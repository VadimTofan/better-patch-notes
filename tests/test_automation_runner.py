from datetime import date, datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


from automation.models import (
    ExtractedChange,
    HttpResponse,
    RegisteredSource,
    SourceDocument,
    SourceRegistry,
)
from automation.runner import (
    REQUIRED_TRANSLATION_LOCALES,
    _qualify_documents,
    _run,
    _translator,
    _validator,
    add_official_localizations,
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
    def test_official_article_matching_ignores_forum_changes(self) -> None:
        # Given a news article and a forum tuning note are collected together
        article_url = (
            "https://news.blizzard.com/en-us/article/24296142/"
            "hotfixes-august-13-2026"
        )
        article = SourceDocument(
            url=article_url,
            channel="live",
            patch="12.1.0",
            title="Hotfixes: August 13, 2026",
            published_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
            updated_at=None,
            author="Blizzard Entertainment",
            author_is_blue=True,
            body=b"<p>English</p>",
            mime_type="text/html",
            locale="en",
            content_hash="article-fixture",
        )
        article_change = ExtractedChange(
            channel="live",
            category="Class",
            effective_date=date(2026, 8, 13),
            patch="12.1.0",
            name="Warlock",
            specialization="All",
            change=("Example change.",),
            source_url=article_url,
        )
        forum_change = ExtractedChange(
            channel="live",
            category="Class",
            effective_date=date(2026, 8, 18),
            patch="12.1.0",
            name="Mage",
            specialization="Arcane",
            change=("All ability damage increased by 3%.",),
            source_url=(
                "https://us.forums.blizzard.com/en/wow/t/"
                "class-tuning-incoming-august-18/2336820/1"
            ),
        )
        document = {"changes": []}

        # When official news localizations are matched
        add_official_localizations(
            document,
            (article_change, forum_change),
            (article,),
        )

        # Then the unrelated forum URL is left for agent translation
        self.assertEqual([], document["changes"])

    def test_collects_announced_changes_before_their_effective_date(self) -> None:
        # Given Blizzard announces a Live class change for the next day
        document = SourceDocument(
            url="https://us.forums.blizzard.com/en/wow/t/topic/1",
            channel="live",
            patch="current",
            title="Class Tuning Incoming – August 18",
            published_at=datetime(2026, 8, 15, tzinfo=timezone.utc),
            updated_at=None,
            author="Linxy",
            author_is_blue=True,
            body=(
                b"<h1><strong>CLASS CHANGES</strong></h1>"
                b"<ul><li><h3><strong>MAGE</strong></h3><ul>"
                b"<li><strong>Arcane</strong><ul>"
                b"<li>All ability damage increased by 3%.</li>"
                b"</ul></li></ul></li></ul>"
            ),
            mime_type="text/html",
            locale="en",
            content_hash="future-live-fixture",
        )

        # When collection qualifies the note before August 18
        result = _qualify_documents(
            (document,),
            "12.1.0",
            date(2026, 8, 17),
        )

        # Then the upcoming change is available with its effective date
        self.assertEqual(1, len(result.accepted))
        self.assertEqual(date(2026, 8, 18), result.accepted[0].effective_date)

    def test_missing_official_article_locale_is_left_for_agent_translation(
        self,
    ) -> None:
        # Given an English article has no current German counterpart
        source_url = (
            "https://news.blizzard.com/en-us/article/24296142/"
            "hotfixes-august-13-2026"
        )
        source = SourceDocument(
            url=source_url,
            channel="live",
            patch="12.1.0",
            title="Hotfixes: August 13, 2026",
            published_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
            updated_at=None,
            author="Blizzard Entertainment",
            author_is_blue=True,
            body=b"<p>English</p>",
            mime_type="text/html",
            locale="en",
            content_hash="fixture-hash",
        )
        change = ExtractedChange(
            channel="live",
            category="Class",
            effective_date=date(2026, 8, 13),
            patch="12.1.0",
            name="Warlock",
            specialization="All",
            change=("Example change.",),
            source_url=source_url,
        )
        document = {
            "changes": [
                {
                    "category": "Class",
                    "date": "2026-08-13",
                    "patch": "12.1.0",
                    "localizations": {
                        "en": {
                            "name": "Warlock",
                            "specialization": "All",
                            "change": ["Example change."],
                        }
                    },
                }
            ]
        }

        # When official localizations are merged
        add_official_localizations(document, (change,), (source,))

        # Then the missing locale remains available for agent translation
        self.assertNotIn(
            "deDE",
            document["changes"][0]["localizations"],
        )

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
            observed_command: list[str] = []

            def write_translation(
                command: list[str],
                _timeout_seconds: int | None = None,
            ) -> str:
                observed_command.extend(command)
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
            checkpoint_paths = [
                observed_command[index + 1]
                for index, argument in enumerate(observed_command)
                if argument == "--checkpoint"
            ]
            self.assertEqual(1, len(checkpoint_paths))
            trusted_checkpoint_index = observed_command.index(
                "--trusted-checkpoint",
            )
            self.assertTrue(
                observed_command[trusted_checkpoint_index + 1].endswith(
                    "data/retail-patch-notes.json",
                )
            )
            self.assertEqual(
                str(root / "translation-checkpoint.json"),
                checkpoint_paths[0],
            )

    def test_translation_process_has_a_twenty_five_minute_budget(self) -> None:
        # Given a translation child process invocation
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")

        # When the bounded runner starts it
        with patch(
            "automation.runner.subprocess.run",
            return_value=completed,
        ) as run:
            _run(["python", "translate.py"], 1500)

        # Then the operating-system timeout leaves validation five minutes
        run.assert_called_once()
        self.assertEqual(1500, run.call_args.kwargs["timeout"])

    def test_translation_failure_returns_an_english_only_batch(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given automatic generation fails before producing an output file
            root = Path(temporary_directory)
            terminology_path = root / "terminology.json"
            terminology_path.write_text("{}", encoding="utf-8")
            error_reason = "placeholder repair failed"
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
                    side_effect=RuntimeError(error_reason),
                ),
                patch("automation.runner.WORK_DIRECTORY", root),
            ):
                batch = _translator(document, terminology_path)

            # Then every locale retains the exact safe generation failure
            self.assertEqual(document["updatedAt"], batch["retrievedAt"])
            self.assertEqual(error_reason, batch["translationGenerationError"])
            self.assertEqual(
                {
                    locale: error_reason
                    for locale in sorted(REQUIRED_TRANSLATION_LOCALES)
                },
                batch["fallbackReasons"],
            )
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

    def test_protects_known_class_taxonomy_with_blizzard_provenance(self) -> None:
        # Given an empty locale registry and the reviewed addon taxonomy
        base = {"schemaVersion": 1, "locales": {"deDE": {"terms": {}}}}
        canonical = {"changes": []}

        # When runtime terminology is prepared
        terminology = build_runtime_terminology(base, canonical)

        # Then class and specialization headings remain verified English terms
        terms = terminology["locales"]["deDE"]["terms"]
        self.assertEqual("Warlock", terms["Warlock"]["localized"])
        self.assertEqual("Blood", terms["Blood"]["localized"])
        self.assertEqual(
            "https://worldofwarcraft.blizzard.com/en-us/game/classes/warlock",
            terms["Warlock"]["sourceUrl"],
        )
        self.assertEqual(
            "https://worldofwarcraft.blizzard.com/en-us/game/classes/death-knight",
            terms["Blood"]["sourceUrl"],
        )

    def test_ignores_an_untranslated_bundled_term(self) -> None:
        # Given contaminated canonical data stores an unknown English heading
        base = {
            "schemaVersion": 1,
            "locales": {"zhTW": {"terms": {}}},
        }
        canonical = {
            "changes": [
                {
                    "localizations": {
                        "en": {
                            "name": "Chronomancer",
                            "specialization": "All",
                        },
                        "zhTW": {
                            "name": "Chronomancer",
                            "specialization": "All",
                            "terminologySourceUrls": [
                                "https://worldofwarcraft.blizzard.com/zh-tw/game/classes/druid"
                            ],
                        },
                    }
                }
            ]
        }

        # When runtime terminology is built from canonical history
        terminology = build_runtime_terminology(base, canonical)

        # Then untranslated text is not promoted as verified terminology
        self.assertNotIn(
            "Chronomancer",
            terminology["locales"]["zhTW"]["terms"],
        )

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
