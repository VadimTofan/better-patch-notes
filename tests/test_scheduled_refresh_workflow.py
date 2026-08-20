from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "scheduled-refresh.yml"


# Describe: unattended Blizzard-only refresh orchestration
class ScheduledRefreshWorkflowTests(unittest.TestCase):
    def test_gates_sequential_locale_jobs_behind_english_acquisition(self) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then
        expected = (
            "acquire:",
            "translate:",
            "aggregate:",
            "needs: acquire",
            "needs.acquire.outputs.outcome == 'DATA_CHANGED'",
            "fail-fast: false",
            "max-parallel: 1",
            "locale: [deDE, esES, esMX, frFR, itIT, koKR, ptBR, ruRU, zhCN, zhTW]",
            "python -m automation.acquisition",
            "python -m automation.translate_locale",
            "python -m automation.aggregate_translations",
            "english-document.json",
            "translation-${{ matrix.locale }}",
            "needs.acquire.outputs.outcome == 'BLOCKED'",
        )
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_declares_the_schedule_concurrency_and_minimum_permissions(self) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then
        expected = (
            'cron: "7 4 * * *"',
            'timezone: "Europe/Copenhagen"',
            "workflow_dispatch:",
            "group: better-patch-notes-refresh",
            "cancel-in-progress: false",
            "contents: write",
            "issues: write",
            "actions: read",
        )
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_runs_all_release_gates_and_calls_the_exact_sha(self) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then
        expected = (
            "python-version: '3.12'",
            "node-version-file: web-app/.nvmrc",
            "GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}",
            "GEMINI_API_KEY2: ${{ secrets.GEMINI_API_KEY2 }}",
            "python -m automation.aggregate_translations",
            "python -m unittest discover -s tests -v",
            "npm test",
            "npm run build",
            "git diff --check",
            "Refresh produced an unauthorized file change",
            'git config user.name "github-actions[bot]"',
            "git add -- BetterPatchNotes.toc Addon.lua README.md",
            "data: refresh retail patch notes for",
            "git push origin HEAD:main",
            "commit_sha: ${{ needs.aggregate.outputs.commit_sha }}",
            "uses: ./.github/workflows/release.yml",
            "CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}",
        )
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)
        self.assertNotIn("git add .", workflow)

    def test_prepares_ignored_website_data_before_running_unit_tests(self) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then
        prepare_position = workflow.find("npm run prepare:data")
        test_position = workflow.find("npm test")
        self.assertGreaterEqual(prepare_position, 0)
        self.assertGreater(test_position, prepare_position)

    def test_short_circuits_no_change_and_manages_failure_reporting(self) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then
        expected = (
            "NO_CHANGE",
            "RELEASE_READY",
            "BLOCKED",
            "if: always()",
            "actions/upload-artifact@",
            "include-hidden-files: true",
            "better-patch-notes-automation",
            "gh issue list",
            "gh issue create",
            "gh issue edit",
            "gh issue close",
            "GITHUB_STEP_SUMMARY",
            "terminologyWarningCount",
            "terminologyWarningsByLocale",
            "needs.aggregate.outputs.dry_run != 'true'",
            "needs.aggregate.outputs.outcome == 'RELEASE_READY'",
            "needs.release.result == 'success'",
            "timeout-minutes: 30",
        )
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_aggregation_runs_after_translation_artifact_download_failure(
        self,
    ) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        download_start = workflow.index(
            "- name: Download locale translation artifacts"
        )
        aggregate_start = workflow.index(
            "- name: Aggregate and coordinate release"
        )
        aggregate_end = workflow.index(
            "- name: Read coordinator result"
        )
        download_step = workflow[download_start:aggregate_start]
        aggregate_step = workflow[aggregate_start:aggregate_end]

        # Then download failure is tolerated and aggregation writes BLOCKED audit
        self.assertIn("continue-on-error: true", download_step)
        self.assertIn("if: always()", aggregate_step)

    def test_reports_unexpected_acquisition_and_aggregation_failures(self) -> None:
        # Given / When
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        report_start = workflow.index(
            "- name: Create or update a blocked-refresh issue"
        )
        report_end = workflow.index(
            "- name: Close the previous blocked-refresh issue"
        )
        report_step = workflow[report_start:report_end]

        # Then unexpected job failures still enter the reporting path
        self.assertIn("Prepare unexpected failure result", workflow)
        self.assertIn("hashFiles('.bpn-work/automation-result.json') == ''", workflow)
        unexpected_start = workflow.index("- name: Prepare unexpected failure result")
        unexpected_end = workflow.index(
            "- name: Create or update a blocked-refresh issue"
        )
        unexpected_step = workflow[unexpected_start:unexpected_end]
        self.assertNotIn("terminologyWarningCount", unexpected_step)
        self.assertNotIn("terminologyWarningsByLocale", unexpected_step)
        self.assertIn("always() &&", report_step)
        self.assertIn("needs.acquire.result == 'failure'", report_step)
        self.assertIn("needs.aggregate.result == 'failure'", report_step)


if __name__ == "__main__":
    unittest.main()
