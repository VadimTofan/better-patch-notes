from datetime import date
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch


from automation.models import HttpResponse, RegisteredSource, SourceRegistry
from automation.runner import (
    _run,
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
