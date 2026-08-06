import unittest


from automation.reporting import (
    build_issue_payload,
    redact_secrets,
    summarize_terminology_warnings,
)


# Describe: safe reporting for unattended refresh failures
class AutomationReportingTests(unittest.TestCase):
    def test_summarizes_terminology_warnings_by_locale(self) -> None:
        # Given repeated preserved-English warnings across two locales
        warnings = (
            "ruRU: Arcane Blast",
            "deDE: Arcane Blast",
            "ruRU: Dark Harvest",
        )

        # When the release-safe summary is built
        summary = summarize_terminology_warnings(warnings)

        # Then totals and deterministic per-locale counts are available
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.by_locale, {"deDE": 1, "ruRU": 2})
        self.assertEqual(
            summary.changelog_text,
            "3 preserved English terminology warnings (deDE: 1; ruRU: 2)",
        )

    def test_builds_a_stable_issue_payload_with_audit_context(self) -> None:
        # Given
        source_urls = (
            "https://news.blizzard.com/en-us/article/1/hotfixes",
            "https://us.forums.blizzard.com/en/wow/t/notes/2/1",
        )

        # When
        title, body = build_issue_payload(
            stage="translation",
            error="ruRU validation failed",
            workflow_url="https://github.com/example/actions/runs/123",
            artifact_name="refresh-audit-123",
            source_urls=source_urls,
        )

        # Then
        self.assertEqual(title, "Automatic patch-note refresh is blocked")
        self.assertIn("<!-- better-patch-notes-automation -->", body)
        self.assertIn("translation", body)
        self.assertIn("refresh-audit-123", body)
        self.assertIn(source_urls[0], body)

    def test_redacts_supported_secret_shapes(self) -> None:
        # Given
        message = (
            "GEMINI_API_KEY=AIzaSyExampleSecret123456789 "
            "auth=AQ.Ab8RN6IUNTmVc7DcBIKNimhOwCZHiQS "
            "CF_API_TOKEN: curse-secret-token"
        )

        # When
        redacted = redact_secrets(message)

        # Then
        self.assertNotIn("AIza", redacted)
        self.assertNotIn("AQ.Ab8", redacted)
        self.assertNotIn("curse-secret-token", redacted)
        self.assertGreaterEqual(redacted.count("[REDACTED]"), 3)


if __name__ == "__main__":
    unittest.main()
