import { describe, expect, it } from "vitest";

import {
  getInitialLocale,
  normalizeBrowserLocale,
  persistLocale,
} from "./locale";

describe("website locale preference", () => {
  it("uses an exact supported browser locale before English fallback", () => {
    // Given a supported regional locale from the browser
    const browserLocales = ["es-MX", "en-US"];

    // When the browser locale is normalized
    const locale = normalizeBrowserLocale(browserLocales);

    // Then the exact regional locale is preserved
    expect(locale).toBe("esMX");
  });

  it("uses the saved cookie before the browser locale", () => {
    // Given a saved locale and a different browser locale
    document.cookie = "bpn_locale=ruRU; Path=/";

    // When the initial preference is resolved
    const locale = getInitialLocale(["fr-FR"]);

    // Then the cookie remains authoritative
    expect(locale).toBe("ruRU");
  });

  it("persists a manual selection in a durable first-party cookie", () => {
    // Given a user selecting Traditional Chinese

    // When the preference is persisted
    persistLocale("zhTW");

    // Then the cookie stores the canonical locale
    expect(document.cookie).toContain("bpn_locale=zhTW");
  });
});
