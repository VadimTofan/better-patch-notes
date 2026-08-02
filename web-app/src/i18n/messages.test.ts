import { describe, expect, it } from "vitest";

import { supportedLocales } from "@/domain/locale.type";
import { localeNames, messages, visibleMessageKeys } from "./messages";

describe("interface translations", () => {
  it("defines every visible label for every supported locale", () => {
    // Given all canonical website locales

    // When each interface dictionary is inspected
    for (const locale of supportedLocales) {
      const dictionary = messages[locale];

      // Then every visible label is populated
      for (const key of visibleMessageKeys) {
        expect(dictionary[key], `${locale}.${key}`).toBeTruthy();
      }
    }
  });

  it("gives every locale a readable native language name", () => {
    // Given the language selector's supported locales

    // When its option labels are inspected
    for (const locale of supportedLocales) {
      // Then each option has a human-readable native label
      expect(localeNames[locale], locale).toBeTruthy();
    }
  });
});
