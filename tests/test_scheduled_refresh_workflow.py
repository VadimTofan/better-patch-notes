from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "scheduled-refresh.yml"


# Describe: unattended Blizzard-only refresh orchestration
class ScheduledRefreshWorkflowTests(unittest.TestCase):
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
            "python -m automation.coordinator",
            "python -m unittest discover -s tests -v",
            "npm test",
            "npm run build",
            "git diff --check",
            "Refresh produced an unauthorized file change",
            'git config user.name "github-actions[bot]"',
            "git add -- BetterPatchNotes.toc Addon.lua README.md",
            "data: refresh retail patch notes for",
            "git push origin HEAD:main",
            "commit_sha: ${{ needs.refresh.outputs.commit_sha }}",
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
        )
        for phrase in expected:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)


if __name__ == "__main__":
    unittest.main()
