import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_PATH = (
    PROJECT_ROOT
    / "skills"
    / "translate-patch-notes"
    / "mcp_server"
    / "workspace.py"
)


def _load_workspace_module():
    if not WORKSPACE_PATH.exists():
        return None

    specification = importlib.util.spec_from_file_location(
        "translation_mcp_workspace",
        WORKSPACE_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Unable to load translation MCP workspace")

    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _canonical_document(updated_at: str = "2026-08-02T19:00:00+02:00"):
    return {
        "schemaVersion": 5,
        "updatedAt": updated_at,
        "changes": [],
    }


# Describe: resumable translation MCP workspace state
class TranslationMcpWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_module = _load_workspace_module()
        self.assertIsNotNone(self.workspace_module)
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.canonical_path = self.root / "retail-patch-notes.json"
        self.work_dir = self.root / ".bpn-work"
        self.canonical_path.write_text(
            json.dumps(_canonical_document()),
            encoding="utf-8",
        )

    def _workspace(self):
        return self.workspace_module.TranslationWorkspace(
            canonical_path=self.canonical_path,
            work_dir=self.work_dir,
        )

    def test_begin_creates_pending_state_for_every_supported_locale(self) -> None:
        # Given canonical patch notes without an existing workspace
        workspace = self._workspace()

        # When a translation workspace begins
        state = workspace.begin()

        # Then all ten non-English locales are pending
        self.assertEqual(1, state["schemaVersion"])
        self.assertEqual(
            "2026-08-02T19:00:00+02:00",
            state["sourceUpdatedAt"],
        )
        self.assertEqual(10, len(state["locales"]))
        self.assertTrue(
            all(
                locale_state["status"] == "pending"
                for locale_state in state["locales"].values()
            )
        )

    def test_begin_resumes_state_for_the_same_canonical_snapshot(self) -> None:
        # Given an existing workspace with a staged German locale
        workspace = self._workspace()
        state = workspace.begin()
        state["locales"]["deDE"]["status"] = "staged"
        workspace.save(state)

        # When the same canonical snapshot begins again
        resumed = workspace.begin()

        # Then the staged progress is preserved
        self.assertEqual("staged", resumed["locales"]["deDE"]["status"])

    def test_begin_rejects_state_from_an_older_canonical_snapshot(self) -> None:
        # Given a workspace created for an earlier canonical snapshot
        workspace = self._workspace()
        workspace.begin()
        self.canonical_path.write_text(
            json.dumps(_canonical_document("2026-08-03T19:00:00+02:00")),
            encoding="utf-8",
        )

        # When the workspace is resumed
        # Then stale progress cannot be mixed with the new source
        with self.assertRaisesRegex(ValueError, "canonical snapshot"):
            workspace.begin()

    def test_begin_rejects_changed_content_with_the_same_updated_at(self) -> None:
        # Given a workspace and later source edits that reuse the timestamp
        workspace = self._workspace()
        workspace.begin()
        changed = _canonical_document()
        changed["changes"] = [{"id": "new-source-record"}]
        self.canonical_path.write_text(
            json.dumps(changed),
            encoding="utf-8",
        )

        # When the workspace is resumed
        # Then a source digest prevents mixed-baseline translations
        with self.assertRaisesRegex(ValueError, "canonical snapshot"):
            workspace.begin()

    def test_save_is_atomic_and_never_changes_canonical_json(self) -> None:
        # Given canonical JSON and a newly created workspace
        original_canonical = self.canonical_path.read_bytes()
        workspace = self._workspace()
        state = workspace.begin()
        state["locales"]["frFR"]["status"] = "staged"

        # When workspace progress is saved
        workspace.save(state)

        # Then canonical data is untouched and no temporary write remains
        self.assertEqual(original_canonical, self.canonical_path.read_bytes())
        self.assertFalse((self.work_dir / "translation-state.tmp").exists())
        persisted = json.loads(
            (self.work_dir / "translation-state.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual("staged", persisted["locales"]["frFR"]["status"])


if __name__ == "__main__":
    unittest.main()
