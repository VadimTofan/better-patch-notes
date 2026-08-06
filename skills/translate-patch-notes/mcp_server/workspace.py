from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


SUPPORTED_TRANSLATION_LOCALES = (
    "deDE",
    "esES",
    "esMX",
    "frFR",
    "itIT",
    "koKR",
    "ptBR",
    "ruRU",
    "zhCN",
    "zhTW",
)


class TranslationWorkspace:
    """Persist resumable translation progress outside canonical addon data."""

    def __init__(self, canonical_path: Path, work_dir: Path) -> None:
        self.canonical_path = canonical_path
        self.work_dir = work_dir
        self.state_path = work_dir / "translation-state.json"
        self.temporary_state_path = work_dir / "translation-state.tmp"

    def begin(self) -> dict[str, object]:
        canonical = self._read_json(self.canonical_path)
        source_digest = sha256(self.canonical_path.read_bytes()).hexdigest()
        source_updated_at = canonical.get("updatedAt")
        if not isinstance(source_updated_at, str) or not source_updated_at:
            raise ValueError("canonical updatedAt must be a non-empty string")

        if self.state_path.exists():
            state = self.load()
            if (
                state.get("sourceUpdatedAt") != source_updated_at
                or state.get("sourceDigest") != source_digest
            ):
                raise ValueError(
                    "workspace canonical snapshot does not match current data"
                )
            return state

        state: dict[str, object] = {
            "schemaVersion": 1,
            "sourceUpdatedAt": source_updated_at,
            "sourceDigest": source_digest,
            "locales": {
                locale: {
                    "status": "pending",
                    "fallbackReason": "",
                    "records": {},
                }
                for locale in SUPPORTED_TRANSLATION_LOCALES
            },
            "terminology": {},
        }
        self.save(state)
        return state

    def load(self) -> dict[str, object]:
        if not self.state_path.exists():
            raise ValueError("translation workspace has not been started")

        return self._read_json(self.state_path)

    def save(self, state: dict[str, object]) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
        self.temporary_state_path.write_text(serialized, encoding="utf-8")
        self.temporary_state_path.replace(self.state_path)

    def status(self) -> dict[str, object]:
        return self.begin()

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"{path.name} must contain a JSON object")

        return document
