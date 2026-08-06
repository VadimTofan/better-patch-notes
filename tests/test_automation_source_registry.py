import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


from automation.source_registry import load_registry


def _valid_registry() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "allowedHosts": [
            "news.blizzard.com",
            "us.forums.blizzard.com",
            "us.version.battle.net",
        ],
        "blueAuthors": ["Kaivax"],
        "maxResponseBytes": 5_000_000,
        "timeoutSeconds": 20,
        "sources": [
            {
                "url": "https://news.blizzard.com/en-us/feed/world-of-warcraft",
                "kind": "news_feed",
                "channel": "live",
                "patch": "current",
                "locale": "en",
                "titlePatterns": ["hotfixes"],
            },
            {
                "url": "https://us.forums.blizzard.com/en/wow/t/2317811",
                "kind": "forum_topic",
                "channel": "ptr",
                "patch": "12.1.0",
                "locale": "en",
                "titlePatterns": ["development notes"],
            },
        ],
    }


def _write_registry(document: dict[str, object], directory: Path) -> Path:
    path = directory / "sources.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    return path


# Describe: trusted Blizzard source registry
class SourceRegistryTests(unittest.TestCase):
    def test_rejects_a_non_blizzard_source_host(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            registry = _valid_registry()
            registry["allowedHosts"].append("wowhead.com")
            path = _write_registry(registry, Path(temporary_directory))

            # When / Then
            with self.assertRaisesRegex(
                ValueError,
                "unsupported Blizzard host",
            ):
                load_registry(path)

    def test_loads_explicit_live_and_ptr_sources(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            path = _write_registry(
                _valid_registry(),
                Path(temporary_directory),
            )

            # When
            registry = load_registry(path)

            # Then
            self.assertEqual(
                {source.channel for source in registry.sources},
                {"live", "ptr"},
            )
            self.assertEqual(registry.max_response_bytes, 5_000_000)
            self.assertEqual(
                {source.patch for source in registry.sources},
                {"current", "12.1.0"},
            )

    def test_rejects_unknown_registry_properties(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given
            registry = _valid_registry()
            registry["unexpected"] = True
            path = _write_registry(registry, Path(temporary_directory))

            # When / Then
            with self.assertRaisesRegex(ValueError, "unknown registry fields"):
                load_registry(path)

    def test_rejects_invalid_limits_and_empty_rules(self) -> None:
        cases = (
            ("maxResponseBytes", 0, "maxResponseBytes"),
            ("timeoutSeconds", 0, "timeoutSeconds"),
            ("blueAuthors", [], "blueAuthors"),
        )

        for field, value, message in cases:
            with self.subTest(field=field):
                with TemporaryDirectory() as temporary_directory:
                    # Given
                    registry = _valid_registry()
                    registry[field] = value
                    path = _write_registry(
                        registry,
                        Path(temporary_directory),
                    )

                    # When / Then
                    with self.assertRaisesRegex(ValueError, message):
                        load_registry(path)


if __name__ == "__main__":
    unittest.main()
