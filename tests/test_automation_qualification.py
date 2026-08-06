from dataclasses import replace
from datetime import date
from pathlib import Path
import unittest


from automation.models import ExtractedChange
from automation.qualification import qualify, resolve_retail_patch


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "blizzard"


def _change(
    *,
    channel: str = "live",
    patch: str = "current",
    effective_date: date = date(2026, 8, 1),
    category: str = "Class",
) -> ExtractedChange:
    return ExtractedChange(
        channel=channel,
        category=category,
        effective_date=effective_date,
        patch=patch,
        name="Mage",
        specialization="Arcane",
        change=("Arcane Blast damage increased by 20%.",),
        source_url="https://news.blizzard.com/en-us/article/1/notes",
    )


# Describe: build and release-window qualification
class QualificationTests(unittest.TestCase):
    def test_resolves_matching_us_and_eu_retail_versions(self) -> None:
        # Given
        response = (FIXTURE_ROOT / "product-versions.txt").read_bytes()

        # When
        patch = resolve_retail_patch((response, response))

        # Then
        self.assertEqual(patch, "12.0.7")

    def test_rejects_disagreement_between_version_responses(self) -> None:
        # Given
        first = (FIXTURE_ROOT / "product-versions.txt").read_bytes()
        second = first.replace(b"12.0.7.68974", b"12.0.8.69000")

        # When / Then
        with self.assertRaisesRegex(ValueError, "disagree"):
            resolve_retail_patch((first, second))

    def test_live_must_match_the_current_retail_patch(self) -> None:
        # Given
        candidate = _change(patch="12.0.8")

        # When
        result = qualify((candidate,), "12.0.7", date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted, ())
        self.assertEqual(result.rejected[0].reason, "live patch mismatch")

    def test_current_live_patch_is_resolved_before_acceptance(self) -> None:
        # Given
        candidate = _change(patch="current")

        # When
        result = qualify((candidate,), "12.0.7", date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted[0].patch, "12.0.7")

    def test_ptr_must_be_newer_than_the_current_retail_patch(self) -> None:
        # Given
        candidate = _change(channel="ptr", patch="12.1.0")

        # When
        result = qualify((candidate,), "12.0.7", date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted, (candidate,))

    def test_rejects_out_of_window_future_and_unsupported_changes(self) -> None:
        # Given
        candidates = (
            _change(effective_date=date(2026, 7, 22)),
            _change(effective_date=date(2026, 8, 6)),
            _change(category="Item"),
        )

        # When
        result = qualify(candidates, "12.0.7", date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted, ())
        self.assertEqual(
            [rejection.reason for rejection in result.rejected],
            [
                "outside rolling 14-day window",
                "effective date is in the future",
                "unsupported category",
            ],
        )

    def test_accepts_the_inclusive_fourteen_day_boundary(self) -> None:
        # Given
        candidate = _change(effective_date=date(2026, 7, 23))

        # When
        result = qualify((candidate,), "12.0.7", date(2026, 8, 5))

        # Then
        self.assertEqual(result.accepted, (replace(candidate, patch="12.0.7"),))


if __name__ == "__main__":
    unittest.main()
