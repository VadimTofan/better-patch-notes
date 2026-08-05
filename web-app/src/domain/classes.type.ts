export const classSlugs = [
  "death-knight",
  "demon-hunter",
  "druid",
  "evoker",
  "hunter",
  "mage",
  "monk",
  "paladin",
  "priest",
  "rogue",
  "shaman",
  "warlock",
  "warrior",
] as const;

export type ClassSlug = (typeof classSlugs)[number];

export interface WowClass {
  slug: ClassSlug;
  englishName: string;
  colorClass: string;
  iconUrl: string;
}
