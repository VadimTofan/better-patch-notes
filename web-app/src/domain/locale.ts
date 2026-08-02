import { supportedLocales, type SupportedLocale } from "./locale.type";

const localeCookieName = "bpn_locale";
const localeAliases: Record<string, SupportedLocale> = {
  de: "deDE",
  dede: "deDE",
  en: "en",
  engb: "en",
  enus: "en",
  es: "esES",
  eses: "esES",
  esmx: "esMX",
  fr: "frFR",
  frfr: "frFR",
  it: "itIT",
  itit: "itIT",
  ko: "koKR",
  kokr: "koKR",
  pt: "ptBR",
  ptbr: "ptBR",
  ru: "ruRU",
  ruru: "ruRU",
  zhcn: "zhCN",
  zhhans: "zhCN",
  zhtw: "zhTW",
  zhhant: "zhTW",
};

function canonicalizeLocale(locale: string): SupportedLocale | undefined {
  const normalized = locale.replace(/[-_]/g, "").toLowerCase();
  return localeAliases[normalized];
}

function getCookieLocale(): SupportedLocale | undefined {
  const cookie = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${localeCookieName}=`));
  const value = cookie?.split("=")[1];

  if (!value || !supportedLocales.includes(value as SupportedLocale)) {
    return undefined;
  }

  return value as SupportedLocale;
}

export function normalizeBrowserLocale(
  browserLocales: readonly string[],
): SupportedLocale {
  for (const locale of browserLocales) {
    const canonicalLocale = canonicalizeLocale(locale);

    if (canonicalLocale) {
      return canonicalLocale;
    }
  }

  return "en";
}

export function getInitialLocale(
  browserLocales: readonly string[] = navigator.languages,
): SupportedLocale {
  return getCookieLocale() ?? normalizeBrowserLocale(browserLocales);
}

export function persistLocale(locale: SupportedLocale): void {
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = [
    `${localeCookieName}=${locale}`,
    `Max-Age=${oneYear}`,
    "Path=/",
    "SameSite=Lax",
  ].join("; ");
}
