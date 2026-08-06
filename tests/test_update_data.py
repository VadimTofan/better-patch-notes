import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPDATER_PATH = (
    PROJECT_ROOT
    / "skills"
    / "fetch-retail-patch-notes"
    / "scripts"
    / "update_data.py"
)


def _change(**overrides: object) -> dict[str, object]:
    localization = {
        "name": "Mage",
        "specialization": "Frost",
        "change": ["Frostbolt damage increased by 5%."],
        "source": "Blizzard",
        "sourceUrl": "https://worldofwarcraft.blizzard.com/example",
    }
    change: dict[str, object] = {
        "channel": "live",
        "category": "Class",
        "date": "2026-07-21",
        "patch": "12.0.7",
        "localizations": {"en": localization},
        "replacesSourceUrl": "",
    }
    localization_fields = {
        "name",
        "specialization",
        "change",
        "source",
        "sourceUrl",
    }
    for field, value in overrides.items():
        if field in localization_fields:
            localization[field] = value
        else:
            change[field] = value

    return change


def _write_batch(path: Path, changes: list[dict[str, object]]) -> None:
    batch = {
        "retrievedAt": "2026-08-01T12:00:00+02:00",
        "changes": changes,
    }
    path.write_text(
        json.dumps(batch, ensure_ascii=False),
        encoding="utf-8",
    )


def _run_updater(
    batch_path: Path,
    data_path: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(UPDATER_PATH),
            "--input",
            str(batch_path),
            "--data",
            str(data_path),
        ],
        capture_output=True,
        check=False,
        text=True,
    )


def _read_data(data_path: Path) -> dict[str, object]:
    return json.loads(data_path.read_text(encoding="utf-8"))


# Describe: canonical JSON creation and validation
class JsonDataCreationTests(unittest.TestCase):
    def test_creates_versioned_json_with_a_stable_change_id(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given one valid Retail class change
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(batch_path, [_change()])

            # When the JSON updater processes the batch
            result = _run_updater(batch_path, data_path)

            # Then it creates the versioned canonical document
            self.assertEqual(0, result.returncode, result.stderr)
            data = _read_data(data_path)
            self.assertEqual(5, data["schemaVersion"])
            self.assertEqual(
                "2026-08-01T12:00:00+02:00",
                data["updatedAt"],
            )
            changes = data["changes"]
            self.assertEqual(1, len(changes))
            stored_change = changes[0]
            self.assertRegex(
                stored_change["id"],
                r"^change-[0-9a-f]{16}$",
            )
            self.assertEqual("Class", stored_change["category"])
            self.assertEqual("live", stored_change["channel"])
            self.assertEqual(
                "https://worldofwarcraft.blizzard.com/example",
                stored_change["localizations"]["en"]["sourceUrl"],
            )
            english = stored_change["localizations"]["en"]
            self.assertEqual("official", english["translationType"])
            self.assertEqual("", english["translatedFrom"])
            self.assertEqual([], english["terminologySourceUrls"])
            self.assertNotIn("replacesSourceUrl", stored_change)

    def test_migrates_schema_three_to_official_provenance(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given one schema-three record without translation provenance
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            legacy_change = _change()
            legacy_change.pop("replacesSourceUrl")
            legacy_change["id"] = "change-0123456789abcdef"
            legacy_change["retrievedAt"] = "2026-07-21T12:00:00+02:00"
            data_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 3,
                        "updatedAt": "2026-07-21T12:00:00+02:00",
                        "changes": [legacy_change],
                    }
                ),
                encoding="utf-8",
            )
            _write_batch(batch_path, [])

            # When the updater opens and republishes the canonical document
            result = _run_updater(batch_path, data_path)

            # Then schema five explicitly marks the legacy text as official
            self.assertEqual(0, result.returncode, result.stderr)
            data = _read_data(data_path)
            self.assertEqual(5, data["schemaVersion"])
            english = data["changes"][0]["localizations"]["en"]
            self.assertEqual("official", english["translationType"])
            self.assertEqual("", english["translatedFrom"])
            self.assertEqual([], english["terminologySourceUrls"])

    def test_migrates_schema_four_english_locales_to_en(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given schema-four data containing both English locale variants
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            legacy_change = _change()
            english = legacy_change["localizations"].pop("en")
            legacy_change["localizations"] = {
                "enGB": {
                    **english,
                    "change": ["British English text."],
                },
                "enUS": {
                    **english,
                    "change": ["Canonical English text."],
                },
            }
            legacy_change.pop("replacesSourceUrl")
            legacy_change["id"] = "change-0123456789abcdef"
            legacy_change["retrievedAt"] = "2026-07-21T12:00:00+02:00"
            data_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 4,
                        "updatedAt": "2026-07-21T12:00:00+02:00",
                        "changes": [legacy_change],
                    }
                ),
                encoding="utf-8",
            )
            _write_batch(batch_path, [])

            # When the updater republishes the canonical document
            result = _run_updater(batch_path, data_path)

            # Then one en localization remains and enUS wins the collision
            self.assertEqual(0, result.returncode, result.stderr)
            data = _read_data(data_path)
            self.assertEqual(5, data["schemaVersion"])
            localizations = data["changes"][0]["localizations"]
            self.assertEqual({"en"}, set(localizations))
            self.assertEqual(
                ["Canonical English text."],
                localizations["en"]["change"],
            )

    def test_requires_en_and_rejects_unknown_locales(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given batches with no English text and with an unknown locale
            temporary_path = Path(temporary_directory)
            missing_english_path = temporary_path / "missing-en.json"
            unknown_locale_path = temporary_path / "unknown-locale.json"
            data_path = temporary_path / "retail-patch-notes.json"
            missing_english = _change()
            missing_english["localizations"] = {
                "deDE": {
                    "name": "Magier",
                    "specialization": "Frost",
                    "change": ["Der Schaden von Frostblitz wurde erhöht."],
                    "source": "Blizzard",
                    "sourceUrl": "https://worldofwarcraft.blizzard.com/de-de/example",
                }
            }
            unknown_locale = _change()
            unknown_locale["localizations"] = {
                **unknown_locale["localizations"],
                "xxXX": {
                    "name": "Mage",
                    "specialization": "Frost",
                    "change": ["Unknown localization."],
                    "source": "Blizzard",
                    "sourceUrl": "https://worldofwarcraft.blizzard.com/example",
                },
            }
            _write_batch(missing_english_path, [missing_english])
            _write_batch(unknown_locale_path, [unknown_locale])

            # When each invalid batch is processed
            missing_result = _run_updater(missing_english_path, data_path)
            unknown_result = _run_updater(unknown_locale_path, data_path)

            # Then both are rejected before canonical data is created
            self.assertNotEqual(0, missing_result.returncode)
            self.assertIn("en", missing_result.stderr.casefold())
            self.assertNotEqual(0, unknown_result.returncode)
            self.assertIn("locale", unknown_result.stderr.casefold())
            self.assertFalse(data_path.exists())

    def test_rejects_an_unknown_channel(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a batch for a channel other than live or PTR
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(batch_path, [_change(channel="beta")])

            # When the updater processes the batch
            result = _run_updater(batch_path, data_path)

            # Then it rejects the unsupported channel
            self.assertNotEqual(0, result.returncode)
            self.assertIn("channel", result.stderr.casefold())
            self.assertFalse(data_path.exists())

    def test_migrates_schema_one_records_to_live_en(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given one canonical schema-one record and an empty batch
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(batch_path, [])
            data_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "updatedAt": "2026-08-01T12:00:00+02:00",
                        "changes": [
                            {
                                "id": "change-0123456789abcdef",
                                "category": "Class",
                                "name": "Mage",
                                "specialization": "Frost",
                                "change": "Frostbolt damage increased by 5%.",
                                "date": "2026-07-21",
                                "patch": "12.0.7",
                                "source": "Blizzard",
                                "sourceUrl": "https://worldofwarcraft.blizzard.com/example",
                                "retrievedAt": "2026-08-01T12:00:00+02:00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            # When the updater reads the old canonical document
            result = _run_updater(batch_path, data_path)

            # Then it migrates the record without changing its stable ID
            self.assertEqual(0, result.returncode, result.stderr)
            data = _read_data(data_path)
            self.assertEqual(5, data["schemaVersion"])
            stored_change = data["changes"][0]
            self.assertEqual("change-0123456789abcdef", stored_change["id"])
            self.assertEqual("live", stored_change["channel"])
            self.assertEqual(
                ["Frostbolt damage increased by 5%."],
                stored_change["localizations"]["en"]["change"],
            )
            self.assertNotIn("change", stored_change)

    def test_rejects_invalid_input_without_changing_existing_data(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given valid canonical data and a batch with an invalid category
            temporary_path = Path(temporary_directory)
            valid_batch_path = temporary_path / "valid.json"
            invalid_batch_path = temporary_path / "invalid.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(valid_batch_path, [_change()])
            valid_result = _run_updater(valid_batch_path, data_path)
            self.assertEqual(0, valid_result.returncode, valid_result.stderr)
            original_data = data_path.read_bytes()
            _write_batch(invalid_batch_path, [_change(category="Delve")])

            # When the invalid batch is processed
            result = _run_updater(invalid_batch_path, data_path)

            # Then validation fails before the canonical file changes
            self.assertNotEqual(0, result.returncode)
            self.assertIn("category", result.stderr.lower())
            self.assertEqual(original_data, data_path.read_bytes())

    def test_rejects_an_unknown_existing_schema_version(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given canonical data from an unsupported future schema
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(batch_path, [_change()])
            data_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": 99,
                        "updatedAt": "2026-08-01T00:00:00+02:00",
                        "changes": [],
                    }
                ),
                encoding="utf-8",
            )
            original_data = data_path.read_bytes()

            # When the updater reads the unsupported schema
            result = _run_updater(batch_path, data_path)

            # Then it refuses migration and preserves the file
            self.assertNotEqual(0, result.returncode)
            self.assertIn("schema", result.stderr.lower())
            self.assertEqual(original_data, data_path.read_bytes())


# Describe: deterministic JSON merge policy
class JsonDataMergeTests(unittest.TestCase):
    def test_groups_same_context_bullets_into_one_record(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given two bullets from the same patch-note section and source
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(
                batch_path,
                [
                    _change(change=["Frostbolt damage increased by 5%."]),
                    _change(change=["Ice Lance damage increased by 3%."]),
                ],
            )

            # When the updater processes the batch
            result = _run_updater(batch_path, data_path)

            # Then one stable record contains both source-ordered bullets
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["added"])
            changes = _read_data(data_path)["changes"]
            self.assertEqual(1, len(changes))
            self.assertEqual(
                [
                    "Frostbolt damage increased by 5%.",
                    "Ice Lance damage increased by 3%.",
                ],
                changes[0]["localizations"]["en"]["change"],
            )

    def test_consolidates_existing_split_records_on_empty_batch(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given canonical data with same-context bullets in separate records
            temporary_path = Path(temporary_directory)
            first_batch_path = temporary_path / "first.json"
            empty_batch_path = temporary_path / "empty.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(first_batch_path, [_change()])
            first_result = _run_updater(first_batch_path, data_path)
            self.assertEqual(0, first_result.returncode, first_result.stderr)
            document = _read_data(data_path)
            original_id = document["changes"][0]["id"]
            second_record = json.loads(json.dumps(document["changes"][0]))
            second_record["id"] = "change-ffffffffffffffff"
            second_record["localizations"]["en"]["change"] = [
                "Ice Lance damage increased by 3%."
            ]
            document["changes"].append(second_record)
            data_path.write_text(
                json.dumps(document, ensure_ascii=False),
                encoding="utf-8",
            )
            _write_batch(empty_batch_path, [])

            # When the updater validates the existing data without new notes
            result = _run_updater(empty_batch_path, data_path)

            # Then it repairs the split records while retaining the first ID
            self.assertEqual(0, result.returncode, result.stderr)
            changes = _read_data(data_path)["changes"]
            self.assertEqual(1, len(changes))
            self.assertEqual(original_id, changes[0]["id"])
            self.assertEqual(
                [
                    "Frostbolt damage increased by 5%.",
                    "Ice Lance damage increased by 3%.",
                ],
                changes[0]["localizations"]["en"]["change"],
            )

    def test_skips_an_exact_duplicate(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given canonical data that already contains a change
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(batch_path, [_change()])
            first_result = _run_updater(batch_path, data_path)
            self.assertEqual(0, first_result.returncode, first_result.stderr)
            original_id = _read_data(data_path)["changes"][0]["id"]

            # When the same normalized change is processed again
            result = _run_updater(batch_path, data_path)

            # Then it is skipped and keeps the same ID
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["skipped"])
            changes = _read_data(data_path)["changes"]
            self.assertEqual(1, len(changes))
            self.assertEqual(original_id, changes[0]["id"])

    def test_promotes_to_blizzard_and_preserves_the_existing_id(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a change first stored from Wowhead
            temporary_path = Path(temporary_directory)
            secondary_path = temporary_path / "secondary.json"
            official_path = temporary_path / "official.json"
            data_path = temporary_path / "retail-patch-notes.json"
            wowhead_url = "https://www.wowhead.com/news/example"
            _write_batch(
                secondary_path,
                [
                    _change(
                        change=["Frostbolt appears to be 5% stronger."],
                        source="Wowhead",
                        sourceUrl=wowhead_url,
                    )
                ],
            )
            secondary_result = _run_updater(secondary_path, data_path)
            self.assertEqual(
                0,
                secondary_result.returncode,
                secondary_result.stderr,
            )
            original_id = _read_data(data_path)["changes"][0]["id"]
            _write_batch(
                official_path,
                [
                    _change(
                        sourceUrl=(
                            "https://worldofwarcraft.blizzard.com/official"
                        ),
                        replacesSourceUrl=wowhead_url,
                    )
                ],
            )

            # When Blizzard confirms the same change
            result = _run_updater(official_path, data_path)

            # Then Blizzard replaces it while the stable ID is retained
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["promoted"])
            changes = _read_data(data_path)["changes"]
            self.assertEqual(1, len(changes))
            self.assertEqual(original_id, changes[0]["id"])
            english = changes[0]["localizations"]["en"]
            self.assertEqual("Blizzard", english["source"])
            self.assertEqual(
                ["Frostbolt damage increased by 5%."],
                english["change"],
            )

    def test_does_not_replace_blizzard_with_a_secondary_source(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given an existing official Blizzard change
            temporary_path = Path(temporary_directory)
            official_path = temporary_path / "official.json"
            secondary_path = temporary_path / "secondary.json"
            data_path = temporary_path / "retail-patch-notes.json"
            blizzard_url = "https://worldofwarcraft.blizzard.com/official"
            _write_batch(
                official_path,
                [_change(sourceUrl=blizzard_url)],
            )
            official_result = _run_updater(official_path, data_path)
            self.assertEqual(
                0,
                official_result.returncode,
                official_result.stderr,
            )
            _write_batch(
                secondary_path,
                [
                    _change(
                        change=["Wowhead paraphrase."],
                        source="Wowhead",
                        sourceUrl="https://www.wowhead.com/news/example",
                        replacesSourceUrl=blizzard_url,
                    )
                ],
            )

            # When the lower-priority source requests replacement
            result = _run_updater(secondary_path, data_path)

            # Then the official record remains authoritative
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["skipped"])
            changes = _read_data(data_path)["changes"]
            self.assertEqual(1, len(changes))
            english = changes[0]["localizations"]["en"]
            self.assertEqual("Blizzard", english["source"])
            self.assertEqual(blizzard_url, english["sourceUrl"])

    def test_keeps_identical_live_and_ptr_changes_separate(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given identical wording published for live and PTR channels
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(
                batch_path,
                [_change(channel="live"), _change(channel="ptr")],
            )

            # When both changes are processed together
            result = _run_updater(batch_path, data_path)

            # Then each channel receives a distinct stable record
            self.assertEqual(0, result.returncode, result.stderr)
            changes = _read_data(data_path)["changes"]
            self.assertEqual(2, len(changes))
            self.assertEqual(
                {"live", "ptr"},
                {change["channel"] for change in changes},
            )
            self.assertEqual(2, len({change["id"] for change in changes}))

    def test_merges_an_official_localization_into_the_existing_change(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given an English record followed by its official German text
            temporary_path = Path(temporary_directory)
            english_path = temporary_path / "english.json"
            localized_path = temporary_path / "localized.json"
            data_path = temporary_path / "retail-patch-notes.json"
            english_change = _change()
            localized_change = _change()
            localized_change["localizations"] = {
                **localized_change["localizations"],
                "deDE": {
                    "name": "Magier",
                    "specialization": "Frost",
                    "change": [
                        "Der Schaden von Frostblitz wurde um 5 % erhöht."
                    ],
                    "source": "Blizzard",
                    "sourceUrl": (
                        "https://worldofwarcraft.blizzard.com/de-de/example"
                    ),
                },
            }
            _write_batch(english_path, [english_change])
            _write_batch(localized_path, [localized_change])
            first_result = _run_updater(english_path, data_path)
            self.assertEqual(0, first_result.returncode, first_result.stderr)
            original_id = _read_data(data_path)["changes"][0]["id"]

            # When the localized version is processed
            result = _run_updater(localized_path, data_path)

            # Then it attaches to the record and preserves its ID
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["localized"])
            changes = _read_data(data_path)["changes"]
            self.assertEqual(1, len(changes))
            self.assertEqual(original_id, changes[0]["id"])
            self.assertEqual(
                "Magier",
                changes[0]["localizations"]["deDE"]["name"],
            )

    def test_rejects_a_non_blizzard_translation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a German localization attributed to a secondary source
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            change = _change()
            change["localizations"] = {
                **change["localizations"],
                "deDE": {
                    "name": "Magier",
                    "specialization": "Frost",
                    "change": ["Der Schaden von Frostblitz wurde erhöht."],
                    "source": "Wowhead",
                    "sourceUrl": "https://www.wowhead.com/de/news/example",
                },
            }
            _write_batch(batch_path, [change])

            # When the updater validates the translated text
            result = _run_updater(batch_path, data_path)

            # Then it rejects unofficial localization data
            self.assertNotEqual(0, result.returncode)
            self.assertIn("blizzard", result.stderr.casefold())
            self.assertFalse(data_path.exists())

    def test_rejects_agent_translation_without_terminology_sources(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given an agent translation without grounded terminology sources
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            change = _change()
            change["localizations"] = {
                **change["localizations"],
                "deDE": {
                    "name": "Magier",
                    "specialization": "Frost",
                    "change": ["Frostblitzschaden wurde um 5 % erhöht."],
                    "source": "Blizzard",
                    "sourceUrl": "https://worldofwarcraft.blizzard.com/example",
                    "translationType": "agent",
                    "translatedFrom": "en",
                    "terminologySourceUrls": [],
                },
            }
            _write_batch(batch_path, [change])

            # When the updater validates the generated localization
            result = _run_updater(batch_path, data_path)

            # Then it rejects ungrounded generated text
            self.assertNotEqual(0, result.returncode)
            self.assertIn("terminologysourceurls", result.stderr.casefold())
            self.assertFalse(data_path.exists())

    def test_official_translation_replaces_agent_translation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given an agent translation followed by official localized text
            temporary_path = Path(temporary_directory)
            agent_path = temporary_path / "agent.json"
            official_path = temporary_path / "official.json"
            data_path = temporary_path / "retail-patch-notes.json"
            agent_change = _change()
            agent_change["localizations"] = {
                **agent_change["localizations"],
                "deDE": {
                    "name": "Magier",
                    "specialization": "Frost",
                    "change": ["Frostblitzschaden wurde um 5 % erhöht."],
                    "source": "Blizzard",
                    "sourceUrl": "https://worldofwarcraft.blizzard.com/example",
                    "translationType": "agent",
                    "translatedFrom": "en",
                    "terminologySourceUrls": [
                        "https://worldofwarcraft.blizzard.com/de-de/game/classes/mage"
                    ],
                },
            }
            official_change = _change()
            official_change["localizations"] = {
                **official_change["localizations"],
                "deDE": {
                    "name": "Magier",
                    "specialization": "Frost",
                    "change": [
                        "Der Schaden von Frostblitz wurde um 5 % erhöht."
                    ],
                    "source": "Blizzard",
                    "sourceUrl": (
                        "https://worldofwarcraft.blizzard.com/de-de/example"
                    ),
                    "translationType": "official",
                    "translatedFrom": "",
                    "terminologySourceUrls": [],
                },
            }
            _write_batch(agent_path, [agent_change])
            _write_batch(official_path, [official_change])
            agent_result = _run_updater(agent_path, data_path)
            self.assertEqual(0, agent_result.returncode, agent_result.stderr)

            # When the current official localization is processed
            result = _run_updater(official_path, data_path)

            # Then official text replaces generated text without changing ID
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["promoted"])
            german = _read_data(data_path)["changes"][0]["localizations"][
                "deDE"
            ]
            self.assertEqual("official", german["translationType"])
            self.assertEqual(
                "Der Schaden von Frostblitz wurde um 5 % erhöht.",
                german["change"][0],
            )

    def test_groups_same_source_and_reports_cross_source_ambiguity(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given similar changes from the same and different articles
            temporary_path = Path(temporary_directory)
            first_path = temporary_path / "first.json"
            same_source_path = temporary_path / "same-source.json"
            other_source_path = temporary_path / "other-source.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(first_path, [_change()])
            first_result = _run_updater(first_path, data_path)
            self.assertEqual(0, first_result.returncode, first_result.stderr)
            _write_batch(
                same_source_path,
                [_change(change=["Frostbolt healing increased by 5%."])],
            )
            same_source_result = _run_updater(
                same_source_path,
                data_path,
            )
            self.assertEqual(
                0,
                same_source_result.returncode,
                same_source_result.stderr,
            )
            _write_batch(
                other_source_path,
                [
                    _change(
                        change=["Frostbolt base damage increased by 5%."],
                        source="Wowhead",
                        sourceUrl="https://www.wowhead.com/news/example",
                    )
                ],
            )

            # When the similar cross-source entry is processed
            result = _run_updater(other_source_path, data_path)

            # Then same-source bullets group and only the other is ambiguous
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(1, json.loads(result.stdout)["ambiguous"])
            changes = _read_data(data_path)["changes"]
            self.assertEqual(2, len(changes))
            official = next(
                change
                for change in changes
                if change["localizations"]["en"]["source"] == "Blizzard"
            )
            self.assertEqual(
                [
                    "Frostbolt damage increased by 5%.",
                    "Frostbolt healing increased by 5%.",
                ],
                official["localizations"]["en"]["change"],
            )

    def test_skips_equivalent_changes_from_the_same_forum_topic(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a stored topic summary and its equivalent post-specific data
            temporary_path = Path(temporary_directory)
            first_path = temporary_path / "first.json"
            repeated_path = temporary_path / "repeated.json"
            data_path = temporary_path / "retail-patch-notes.json"
            topic_url = "https://us.forums.blizzard.com/en/wow/t/notes/123"
            _write_batch(
                first_path,
                [
                    _change(
                        change=[
                            "Boss – Strike: Damage reduced by 10%.",
                            "Boss: Health reduced by 5%.",
                        ],
                        sourceUrl=topic_url,
                    )
                ],
            )
            _write_batch(
                repeated_path,
                [
                    _change(
                        change=[
                            "Boss: Health reduced by 5%",
                            "Boss — Strike: Damage reduced by 10%",
                        ],
                        sourceUrl=f"{topic_url}/5",
                    )
                ],
            )
            first_result = _run_updater(first_path, data_path)
            self.assertEqual(0, first_result.returncode, first_result.stderr)

            # When the post-specific formatting variant is processed
            result = _run_updater(repeated_path, data_path)

            # Then it is recognized as the same official change set
            self.assertEqual(0, result.returncode, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(0, report["ambiguous"])
            self.assertEqual(1, report["skipped"])
            self.assertEqual(1, len(_read_data(data_path)["changes"]))

    def test_sorts_newest_changes_first_with_stable_tie_breakers(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given changes supplied in a non-deterministic order
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(
                batch_path,
                [
                    _change(
                        category="Raid",
                        name="The Voidspire",
                        specialization="",
                        change=["Older raid change."],
                        date="2026-07-01",
                    ),
                    _change(
                        name="Druid",
                        specialization="Balance",
                        change=["Newer druid change."],
                        date="2026-07-28",
                    ),
                    _change(
                        change=["Newer mage change."],
                        date="2026-07-28",
                    ),
                ],
            )

            # When the canonical data is updated
            result = _run_updater(batch_path, data_path)

            # Then dates descend and equal dates use stable alphabetical keys
            self.assertEqual(0, result.returncode, result.stderr)
            changes = _read_data(data_path)["changes"]
            self.assertEqual(
                ["Druid", "Mage", "The Voidspire"],
                [
                    change["localizations"]["en"]["name"]
                    for change in changes
                ],
            )

    def test_leaves_no_temporary_json_after_success(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            # Given a valid batch in an otherwise empty directory
            temporary_path = Path(temporary_directory)
            batch_path = temporary_path / "batch.json"
            data_path = temporary_path / "retail-patch-notes.json"
            _write_batch(batch_path, [_change()])

            # When the data is saved successfully
            result = _run_updater(batch_path, data_path)

            # Then no temporary files remain
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual([], list(temporary_path.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
