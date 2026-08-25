import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


from automation.source_registry import load_registry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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

    def test_project_registry_has_no_ptr_sources_without_an_active_ptr(self) -> None:
        # Given the reviewed project registry for the current Live-only cycle
        registry_path = PROJECT_ROOT / "automation" / "sources.json"

        # When the configured sources are loaded
        registry = load_registry(registry_path)

        # Then unattended discovery does not treat old Live notes as PTR
        self.assertNotIn(
            "ptr",
            {source.channel for source in registry.sources},
        )

    def test_project_registry_excludes_superseded_august_18_topic(self) -> None:
        # Given Blizzard incorporated the forum changes into its hotfix article
        registry_path = PROJECT_ROOT / "automation" / "sources.json"

        # When the configured sources are loaded
        registry = load_registry(registry_path)

        # Then the superseded topic is no longer polled as a separate source
        self.assertNotIn(
            "2336820",
            "\n".join(source.url for source in registry.sources),
        )

    def test_project_registry_discovers_live_tuning_forum_categories(self) -> None:
        # Given the reviewed project registry for unattended Live discovery
        registry_path = PROJECT_ROOT / "automation" / "sources.json"

        # When the configured sources are loaded
        registry = load_registry(registry_path)

        # Then both official Live forum categories are monitored narrowly
        forum_sources = {
            source.url: source
            for source in registry.sources
            if source.kind == "forum_category"
        }
        self.assertEqual(
            set(forum_sources),
            {
                "https://us.forums.blizzard.com/en/wow/c/171.json",
                "https://us.forums.blizzard.com/en/wow/c/40.json",
            },
        )
        self.assertEqual(
            forum_sources[
                "https://us.forums.blizzard.com/en/wow/c/171.json"
            ].title_patterns,
            ("class tuning incoming",),
        )
        self.assertEqual(
            forum_sources[
                "https://us.forums.blizzard.com/en/wow/c/40.json"
            ].title_patterns,
            ("tuning changes", "adjustments"),
        )

    def test_project_registry_accepts_verified_nymrissa_blue_author(self) -> None:
        # Given the reviewed project registry for official forum authors
        registry_path = PROJECT_ROOT / "automation" / "sources.json"

        # When the configured registry is loaded
        registry = load_registry(registry_path)

        # Then the verified Blizzard developer can publish eligible notes
        self.assertIn("Limestone-1964469", registry.blue_authors)

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
