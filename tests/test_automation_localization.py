from datetime import datetime, timezone
import unittest

from automation.localization import align_official_localizations
from automation.models import ExtractedChange, SourceDocument


def _document(locale: str, body: str) -> SourceDocument:
    return SourceDocument(
        url=f"https://news.blizzard.com/{locale}/article/1/notes",
        channel="live",
        patch="12.0.7",
        locale=locale,
        title="Notes",
        author="Blizzard Entertainment",
        published_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        updated_at=None,
        body=body.encode(),
        mime_type="text/html",
        content_hash=locale,
        author_is_blue=True,
    )


class OfficialLocalizationAlignmentTests(unittest.TestCase):
    def test_aligns_localized_headings_and_bullets_by_reviewed_structure(self):
        # Given structurally identical English and German Blizzard articles
        english = _document(
            "en",
            "<h2>Classes</h2><h3>Death Knight</h3>"
            "<ul><li>Frost<ul><li>Damage increased by 5%.</li></ul></li></ul>",
        )
        german = _document(
            "deDE",
            "<h2>Klassen</h2><h3>Todesritter</h3>"
            "<ul><li>Frost<ul><li>Schaden um 5% erhöht.</li></ul></li></ul>",
        )
        changes = (
            ExtractedChange(
                channel="live",
                category="Class",
                effective_date=english.published_at.date(),
                patch="12.0.7",
                name="Death Knight",
                specialization="Frost",
                change=("Damage increased by 5%.",),
                source_url=english.url,
            ),
        )

        # When official localized content is aligned
        aligned = align_official_localizations(english, german, changes)

        # Then exact Blizzard text and localized headings are returned
        self.assertEqual("Todesritter", aligned[0].name)
        self.assertEqual("Frost", aligned[0].specialization)
        self.assertEqual(("Schaden um 5% erhöht.",), aligned[0].change)

    def test_rejects_a_localized_article_with_different_structure(self):
        # Given Blizzard's localized article omits one nested list
        english = _document(
            "en",
            "<h2>Classes</h2><ul><li>Damage increased.</li></ul>",
        )
        german = _document(
            "deDE",
            "<h2>Klassen</h2><p>Schaden erhöht.</p>",
        )

        # When / Then unsafe positional alignment is rejected
        with self.assertRaisesRegex(ValueError, "structure does not match"):
            align_official_localizations(english, german, ())


if __name__ == "__main__":
    unittest.main()
