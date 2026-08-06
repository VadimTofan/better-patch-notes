import json
from pathlib import Path
import unittest


from automation.discovery import (
    UnsupportedSourceShape,
    discover_forum_documents,
    discover_forum_topic_urls,
    discover_news_documents,
)
from automation.models import RegisteredSource


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "blizzard"


def _news_source() -> RegisteredSource:
    return RegisteredSource(
        url="https://news.blizzard.com/en-us/feed/world-of-warcraft",
        kind="news_feed",
        channel="live",
        patch="current",
        locale="en",
        title_patterns=("hotfixes",),
    )


def _forum_source() -> RegisteredSource:
    return RegisteredSource(
        url="https://us.forums.blizzard.com/en/wow/t/2317811",
        kind="forum_topic",
        channel="ptr",
        patch="12.1.0",
        locale="en",
        title_patterns=("development notes",),
    )


# Describe: discovery of eligible official Blizzard documents
class BlizzardDiscoveryTests(unittest.TestCase):
    def test_discovers_matching_topics_from_the_reviewed_ptr_category(self) -> None:
        # Given
        category = (FIXTURE_ROOT / "forum-category.json").read_bytes()
        source = RegisteredSource(
            url="https://us.forums.blizzard.com/en/wow/c/341.json",
            kind="forum_category",
            channel="ptr",
            patch="12.1.0",
            locale="en",
            title_patterns=("development notes", "dungeon test"),
        )

        # When
        urls = discover_forum_topic_urls(category, source)

        # Then
        self.assertEqual(
            urls,
            (
                "https://us.forums.blizzard.com/en/wow/t/2317811.json",
                "https://us.forums.blizzard.com/en/wow/t/2330956.json",
            ),
        )

    def test_accepts_only_blue_authored_forum_posts(self) -> None:
        # Given
        topic = (FIXTURE_ROOT / "forum-topic.json").read_bytes()

        # When
        documents = discover_forum_documents(
            topic,
            _forum_source(),
            frozenset({"Linxy"}),
        )

        # Then
        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0].author_is_blue)
        self.assertEqual(documents[0].channel, "ptr")
        self.assertTrue(documents[0].url.endswith("/2317811/18"))

    def test_rejects_an_allowlisted_name_without_current_staff_metadata(self) -> None:
        # Given
        topic = json.loads(
            (FIXTURE_ROOT / "forum-topic.json").read_text(encoding="utf-8")
        )
        topic["post_stream"]["posts"][0]["staff"] = False

        # When
        documents = discover_forum_documents(
            json.dumps(topic).encode(),
            _forum_source(),
            frozenset({"Linxy"}),
        )

        # Then
        self.assertEqual(documents, ())

    def test_skips_staff_topic_actions_without_patch_note_content(self) -> None:
        # Given
        topic = json.loads(
            (FIXTURE_ROOT / "forum-topic.json").read_text(encoding="utf-8")
        )
        action = dict(topic["post_stream"]["posts"][0])
        action["post_number"] = 17
        action["post_type"] = 3
        action["cooked"] = ""
        topic["post_stream"]["posts"].append(action)

        # When
        documents = discover_forum_documents(
            json.dumps(topic).encode(),
            _forum_source(),
            frozenset({"Linxy"}),
        )

        # Then
        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0].url.endswith("/18"))

    def test_discovers_only_matching_news_titles(self) -> None:
        # Given
        feed = (FIXTURE_ROOT / "news-feed.json").read_bytes()

        # When
        documents = discover_news_documents(feed, _news_source())

        # Then
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].title, "Hotfixes: August 4, 2026")
        self.assertEqual(documents[0].channel, "live")
        self.assertEqual(
            documents[0].url,
            "https://news.blizzard.com/en-us/article/24299999/"
            "hotfixes-august-4-2026",
        )

    def test_rejects_an_unknown_feed_shape(self) -> None:
        # Given
        malformed_feed = b'{"feed": {"unexpected": []}}'

        # When / Then
        with self.assertRaisesRegex(UnsupportedSourceShape, "news feed"):
            discover_news_documents(malformed_feed, _news_source())

    def test_rejects_a_forum_topic_without_required_fields(self) -> None:
        # Given
        malformed_topic = json.dumps({"title": "Development Notes"}).encode()

        # When / Then
        with self.assertRaisesRegex(UnsupportedSourceShape, "forum topic"):
            discover_forum_documents(
                malformed_topic,
                _forum_source(),
                frozenset({"Linxy"}),
            )

    def test_returns_documents_in_stable_time_and_url_order(self) -> None:
        # Given
        topic = json.loads(
            (FIXTURE_ROOT / "forum-topic.json").read_text(encoding="utf-8")
        )
        second_blue_post = dict(topic["post_stream"]["posts"][0])
        second_blue_post["post_number"] = 17
        second_blue_post["created_at"] = "2026-07-30T18:49:00Z"
        topic["post_stream"]["posts"].append(second_blue_post)

        # When
        documents = discover_forum_documents(
            json.dumps(topic).encode(),
            _forum_source(),
            frozenset({"Linxy"}),
        )

        # Then
        self.assertEqual(
            [document.url.rsplit("/", 1)[-1] for document in documents],
            ["17", "18"],
        )


if __name__ == "__main__":
    unittest.main()
