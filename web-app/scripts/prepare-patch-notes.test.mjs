import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { preparePatchNotes } from "./prepare-patch-notes.mjs";

const validPatchNotes = {
  schemaVersion: 5,
  updatedAt: "2026-08-02T12:00:00Z",
  changes: [
    {
      id: "druid-live-test",
      channel: "live",
      category: "Class",
      class: "Druid",
      classToken: "DRUID",
      specialization: "Balance",
      specializationId: 102,
      dungeon: "",
      raid: "",
      effectiveDate: "2026-08-01",
      patch: "12.0.1",
      source: {
        name: "Blizzard",
        url: "https://worldofwarcraft.blizzard.com/",
        publishedAt: "2026-08-01T12:00:00Z",
      },
      localizations: {
        en: {
          change: ["Moonfire damage increased by 5%."],
          class: "Druid",
          specialization: "Balance",
          dungeon: "",
          raid: "",
          translationType: "official",
          translatedFrom: "",
          terminologySourceUrls: [],
        },
      },
    },
  ],
};

// Describe: canonical patch-note preparation
test("copies a valid schema-five data snapshot for the website", async () => {
  // Given a valid canonical patch-note file
  const directory = await mkdtemp(join(tmpdir(), "bpn-web-data-"));
  const sourcePath = join(directory, "source.json");
  const outputPath = join(directory, "generated", "patch-notes.json");
  await writeFile(sourcePath, JSON.stringify(validPatchNotes), "utf8");

  // When the website snapshot is prepared
  await preparePatchNotes({ sourcePath, outputPath });

  // Then the generated snapshot preserves canonical content exactly
  const generated = JSON.parse(await readFile(outputPath, "utf8"));
  assert.deepEqual(generated, validPatchNotes);
});

test("rejects unsupported schema data before writing website output", async () => {
  // Given canonical data with an unsupported schema version
  const directory = await mkdtemp(join(tmpdir(), "bpn-web-data-"));
  const sourcePath = join(directory, "source.json");
  const outputPath = join(directory, "generated", "patch-notes.json");
  const invalidPatchNotes = { ...validPatchNotes, schemaVersion: 4 };
  await writeFile(sourcePath, JSON.stringify(invalidPatchNotes), "utf8");

  // When the website snapshot is prepared
  const preparation = preparePatchNotes({ sourcePath, outputPath });

  // Then it fails with a clear schema diagnostic
  await assert.rejects(preparation, /schemaVersion must be 5/);
});
