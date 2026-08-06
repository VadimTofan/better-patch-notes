from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "release.yml"
TOC_PATH = PROJECT_ROOT / "BetterPatchNotes.toc"
NETLIFY_PATH = PROJECT_ROOT / "netlify.toml"


# Describe: automatic CurseForge releases
class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_can_run_for_an_exact_reusable_commit(self) -> None:
        # Given a scheduled refresh that creates a release commit with GITHUB_TOKEN
        expected_phrases = (
            "workflow_call:",
            "commit_sha:",
            "required: false",
            "CF_API_TOKEN:",
            "required: true",
            "ref: ${{ inputs.commit_sha || github.sha }}",
            "value: ${{ jobs.release.outputs.version }}",
            "value: ${{ jobs.release.outputs.tag }}",
            "value: ${{ jobs.release.outputs.file_id }}",
            "version: ${{ steps.validate.outputs.version }}",
            "tag: ${{ steps.validate.outputs.tag }}",
            "file_id: ${{ steps.upload.outputs.file_id }}",
            "id: upload",
            'echo "file_id=$file_id" >> "$GITHUB_OUTPUT"',
        )

        # When the release workflow contract is inspected
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then callers can release and audit one exact commit
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_netlify_builds_the_vue_spa_from_the_web_app(self) -> None:
        # Given the public website deployment configuration
        expected_phrases = (
            'base = "web-app"',
            'command = "npm run build"',
            'publish = "dist"',
            'NODE_VERSION = "24.15.0"',
            'from = "/*"',
            'to = "/index.html"',
            "status = 200",
        )

        # When the Netlify configuration is inspected
        configuration = NETLIFY_PATH.read_text(encoding="utf-8")

        # Then production builds and direct class routes are supported
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, configuration)

    def test_web_only_pushes_do_not_trigger_curseforge_releases(self) -> None:
        # Given one repository containing the addon and public website
        expected_runtime_paths = (
            "BetterPatchNotes.toc",
            "Addon.lua",
            "Localization.lua",
            "PatchNotesData.lua",
            "Data.lua",
            "State.lua",
            "Window.lua",
            "MinimapButton.lua",
            "Core.lua",
            "changelog.txt",
        )

        # When the CurseForge workflow push filters are inspected
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        push_start = workflow.find("push:")
        dispatch_start = workflow.find("workflow_dispatch:")
        push_filter = workflow[push_start:dispatch_start]

        # Then addon runtime changes trigger releases and website changes do not
        self.assertIn("paths:", push_filter)
        for runtime_path in expected_runtime_paths:
            with self.subTest(runtime_path=runtime_path):
                self.assertIn(runtime_path, push_filter)
        self.assertNotIn("web-app", push_filter)
        self.assertNotIn("netlify.toml", push_filter)

    def test_main_push_publishes_the_validated_addon_to_curseforge(
        self,
    ) -> None:
        # Given the approved automatic release workflow
        expected_phrases = (
            "push:",
            "branches: [main]",
            "workflow_dispatch:",
            "Validate release inputs",
            "required_files=(",
            '"MinimapButton.lua"',
            "Release versions are not synchronized",
            "CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}",
            "Package runtime addon",
            "BetterPatchNotes-v$version.zip",
            "Upload release to CurseForge",
            "https://wow.curseforge.com/api/projects/1635519/upload-file",
            'X-Api-Token: $CF_API_TOKEN',
            "curl --fail-with-body",
            "releaseType: \"release\"",
        )

        # When the GitHub Actions workflow is inspected
        workflow_exists = WORKFLOW_PATH.exists()
        workflow = (
            WORKFLOW_PATH.read_text(encoding="utf-8")
            if workflow_exists
            else ""
        )

        # Then pushes to main are tested and published with a private token
        self.assertTrue(
            workflow_exists,
            f"Release workflow is missing: {WORKFLOW_PATH}",
        )
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)
        self.assertNotIn("BigWigsMods/packager", workflow)
        self.assertNotIn("unittest discover", workflow)

    def test_release_is_tagged_from_the_toc_version_after_upload(self) -> None:
        # Given a stable release whose version is declared by the addon TOC
        expected_phrases = (
            "version=\"$(sed -n 's/^## Version: //p' "
            "BetterPatchNotes.toc)\"",
            "Release tag already exists:",
            "Upload release to CurseForge",
            'git config user.name "github-actions[bot]"',
            'git config user.email "41898282+github-actions[bot]@users.',
            "git tag --annotate",
            "git push origin",
        )

        # When the release steps are inspected in execution order
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then the stable tag is created and pushed only after upload
        positions = []
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                position = workflow.find(phrase)
                self.assertNotEqual(-1, position, f"Missing: {phrase}")
                positions.append(position)

        self.assertEqual(sorted(positions), positions)

    def test_upload_resolves_retail_game_version_and_preserves_errors(
        self,
    ) -> None:
        # Given a WoW release whose interface maps to a CurseForge version
        expected_phrases = (
            "interface=\"$(sed -n 's/^## Interface: //p'",
            "game_version=",
            "https://wow.curseforge.com/api/game/wow/versions",
            "gameVersionTypeID == 517",
            "gameVersions: [$game_version_id]",
            '--form "metadata=<-"',
            '--output "$versions_response_file"',
            '--output "$upload_response_file"',
            "print_api_error",
        )

        # When the CurseForge upload step is inspected
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        # Then it sends a valid retail version and retains API diagnostics
        for phrase in expected_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, workflow)

    def test_package_step_lists_only_runtime_files(self) -> None:
        # Given the exact set of files loaded by the addon at runtime
        runtime_files = (
            "BetterPatchNotes.toc",
            "Addon.lua",
            "Localization.lua",
            "PatchNotesData.lua",
            "Data.lua",
            "State.lua",
            "Window.lua",
            "MinimapButton.lua",
            "Core.lua",
            "changelog.txt",
        )
        development_files = (
            "README.md",
            "LICENSE",
            ".pkgmeta",
            "AGENTS.md",
        )

        # When the direct packaging step is inspected
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        package_start = workflow.find("- name: Package runtime addon")
        upload_start = workflow.find("- name: Upload release to CurseForge")
        package_step = workflow[package_start:upload_start]

        # Then it packages every runtime file and no development-only file
        self.assertGreaterEqual(package_start, 0)
        self.assertGreater(upload_start, package_start)
        for file_name in runtime_files:
            with self.subTest(file_name=file_name):
                self.assertIn(f'"{file_name}"', package_step)
        for file_name in development_files:
            with self.subTest(file_name=file_name):
                self.assertNotIn(f'"{file_name}"', package_step)

    def test_manifest_declares_the_curseforge_project(self) -> None:
        # Given the addon manifest used by the direct release workflow

        # When its CurseForge metadata is inspected
        toc = TOC_PATH.read_text(encoding="utf-8-sig")

        # Then it declares the approved CurseForge project
        self.assertIn("## X-Curse-Project-ID: 1635519", toc)


if __name__ == "__main__":
    unittest.main()
