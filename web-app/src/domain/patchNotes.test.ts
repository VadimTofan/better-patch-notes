import { describe, expect, it } from "vitest";

import type { PatchNoteRecord } from "./patchNotes.type";
import {
  getSafeSourceUrl,
  getVisiblePatchNotes,
  localizeRecord,
} from "./patchNotes";

const druidNote: PatchNoteRecord = {
  id: "druid-note",
  channel: "live",
  category: "Class",
  date: "2026-08-01",
  patch: "12.0.1",
  retrievedAt: "2026-08-02T12:00:00Z",
  localizations: {
    en: {
      name: "Druid",
      specialization: "Balance",
      source: "Blizzard",
      sourceUrl: "https://worldofwarcraft.blizzard.com/",
      translationType: "official",
      translatedFrom: "",
      change: ["Moonfire damage increased by 5%."],
      terminologySourceUrls: [],
    },
    deDE: {
      name: "Druide",
      specialization: "Gleichgewicht",
      source: "Blizzard",
      sourceUrl: "https://worldofwarcraft.blizzard.com/de-de/",
      translationType: "official",
      translatedFrom: "",
      change: ["Mondfeuerschaden wurde um 5 % erhöht."],
      terminologySourceUrls: [],
    },
  },
};

const dungeonNote: PatchNoteRecord = {
  ...druidNote,
  id: "dungeon-note",
  category: "Dungeon",
  localizations: {
    en: {
      ...druidNote.localizations.en,
      name: "Ruby Life Pools",
      specialization: "",
    },
  },
};

describe("patch-note selection and localization", () => {
  it("accepts secure source links", () => {
    // Given a secure patch-note source URL
    const sourceUrl = "https://worldofwarcraft.blizzard.com/news/patch-notes";

    // When the URL is checked for display
    const safeSourceUrl = getSafeSourceUrl(sourceUrl);

    // Then the secure URL is returned unchanged
    expect(safeSourceUrl).toBe(sourceUrl);
  });

  it("rejects source links that are not secure", () => {
    // Given an insecure patch-note source URL
    const sourceUrl = "http://worldofwarcraft.blizzard.com/news/patch-notes";

    // When the URL is checked for display
    const safeSourceUrl = getSafeSourceUrl(sourceUrl);

    // Then no source URL is exposed
    expect(safeSourceUrl).toBeNull();
  });

  it("filters the active class and keeps dungeon notes independent", () => {
    // Given notes for a class and a dungeon
    const records = [druidNote, dungeonNote];

    // When Druid Live notes are selected
    const visible = getVisiblePatchNotes(records, "druid", "live");

    // Then both the Druid and global dungeon notes are returned by section
    expect(visible.classNotes).toEqual([druidNote]);
    expect(visible.dungeonNotes).toEqual([dungeonNote]);
    expect(visible.raidNotes).toEqual([]);
  });

  it("falls back to English and reports the fallback", () => {
    // Given a dungeon note without a French localization

    // When it is localized for French
    const localized = localizeRecord(dungeonNote, "frFR");

    // Then English text is shown with a fallback marker
    expect(localized.content.name).toBe("Ruby Life Pools");
    expect(localized.usedFallback).toBe(true);
  });

  it("uses an exact translated locale when one exists", () => {
    // Given a German localization for a Druid note

    // When the note is localized for German
    const localized = localizeRecord(druidNote, "deDE");

    // Then the German record is returned without fallback
    expect(localized.content.name).toBe("Druide");
    expect(localized.usedFallback).toBe(false);
  });
});
