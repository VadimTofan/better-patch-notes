import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import type { PatchNoteRecord } from "@/domain/patchNotes.type";

import PatchSection from "./PatchSection.vue";

const localizedNote: PatchNoteRecord = {
  id: "localized-source-note",
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
      sourceUrl: "https://worldofwarcraft.blizzard.com/en-us/news",
      translationType: "official",
      translatedFrom: "",
      change: ["Moonfire damage increased by 5%."],
      terminologySourceUrls: [],
    },
    deDE: {
      name: "Druide",
      specialization: "Gleichgewicht",
      source: "Blizzard",
      sourceUrl: "https://worldofwarcraft.blizzard.com/de-de/news",
      translationType: "official",
      translatedFrom: "",
      change: ["Mondfeuerschaden wurde um 5 % erhöht."],
      terminologySourceUrls: [],
    },
  },
};

describe("PatchSection source links", () => {
  it("opens the displayed locale source in a safe new tab", () => {
    // Given a German note with its own official source
    const wrapper = mount(PatchSection, {
      props: {
        title: "Klassenänderungen",
        notes: [localizedNote],
        locale: "deDE",
        expanded: true,
      },
    });

    // When the localized note card is rendered
    const sourceLink = wrapper.get("[data-testid='source-link']");

    // Then it links to the German source without replacing website state
    expect(sourceLink.attributes("href")).toBe(
      "https://worldofwarcraft.blizzard.com/de-de/news",
    );
    expect(sourceLink.attributes("target")).toBe("_blank");
    expect(sourceLink.attributes("rel")).toBe("noopener noreferrer");
    expect(sourceLink.text()).toContain("Quelle");
  });

  it("uses the English source when the displayed note falls back", () => {
    // Given a note without a French localization
    const wrapper = mount(PatchSection, {
      props: {
        title: "Modifications de classe",
        notes: [localizedNote],
        locale: "frFR",
        expanded: true,
      },
    });

    // When the English fallback note is rendered
    const sourceLink = wrapper.get("[data-testid='source-link']");

    // Then its Source control points to the displayed English record
    expect(sourceLink.attributes("href")).toBe(
      "https://worldofwarcraft.blizzard.com/en-us/news",
    );
  });

  it("hides an unsafe source URL", () => {
    // Given a note whose displayed localization has an insecure source
    const unsafeNote: PatchNoteRecord = {
      ...localizedNote,
      id: "unsafe-source-note",
      localizations: {
        en: {
          ...localizedNote.localizations.en,
          sourceUrl: "javascript:alert('unsafe')",
        },
      },
    };
    const wrapper = mount(PatchSection, {
      props: {
        title: "Class changes",
        notes: [unsafeNote],
        locale: "en",
        expanded: true,
      },
    });

    // When the note card is rendered
    const sourceLink = wrapper.find("[data-testid='source-link']");

    // Then no clickable source is exposed
    expect(sourceLink.exists()).toBe(false);
  });
});
