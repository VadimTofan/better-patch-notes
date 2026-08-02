export const supportedLocales = [
  "deDE",
  "en",
  "esES",
  "esMX",
  "frFR",
  "itIT",
  "koKR",
  "ptBR",
  "ruRU",
  "zhCN",
  "zhTW",
] as const;

export type SupportedLocale = (typeof supportedLocales)[number];
