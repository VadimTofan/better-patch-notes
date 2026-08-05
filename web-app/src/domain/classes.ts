import type { ClassSlug, WowClass } from "./classes.type";

const iconRoot = "https://render.worldofwarcraft.com/us/icons/56";

export const wowClasses: readonly WowClass[] = [
  {
    slug: "death-knight",
    englishName: "Death Knight",
    colorClass: "[--class-color:#c41e3a]",
    iconUrl: `${iconRoot}/classicon_deathknight.jpg`,
  },
  {
    slug: "demon-hunter",
    englishName: "Demon Hunter",
    colorClass: "[--class-color:#a330c9]",
    iconUrl: `${iconRoot}/classicon_demonhunter.jpg`,
  },
  {
    slug: "druid",
    englishName: "Druid",
    colorClass: "[--class-color:#ff7c0a]",
    iconUrl: `${iconRoot}/classicon_druid.jpg`,
  },
  {
    slug: "evoker",
    englishName: "Evoker",
    colorClass: "[--class-color:#33937f]",
    iconUrl: `${iconRoot}/classicon_evoker.jpg`,
  },
  {
    slug: "hunter",
    englishName: "Hunter",
    colorClass: "[--class-color:#aad372]",
    iconUrl: `${iconRoot}/classicon_hunter.jpg`,
  },
  {
    slug: "mage",
    englishName: "Mage",
    colorClass: "[--class-color:#3fc7eb]",
    iconUrl: `${iconRoot}/classicon_mage.jpg`,
  },
  {
    slug: "monk",
    englishName: "Monk",
    colorClass: "[--class-color:#00ff98]",
    iconUrl: `${iconRoot}/classicon_monk.jpg`,
  },
  {
    slug: "paladin",
    englishName: "Paladin",
    colorClass: "[--class-color:#f48cba]",
    iconUrl: `${iconRoot}/classicon_paladin.jpg`,
  },
  {
    slug: "priest",
    englishName: "Priest",
    colorClass: "[--class-color:#ffffff]",
    iconUrl: `${iconRoot}/classicon_priest.jpg`,
  },
  {
    slug: "rogue",
    englishName: "Rogue",
    colorClass: "[--class-color:#fff468]",
    iconUrl: `${iconRoot}/classicon_rogue.jpg`,
  },
  {
    slug: "shaman",
    englishName: "Shaman",
    colorClass: "[--class-color:#0070dd]",
    iconUrl: `${iconRoot}/classicon_shaman.jpg`,
  },
  {
    slug: "warlock",
    englishName: "Warlock",
    colorClass: "[--class-color:#8788ee]",
    iconUrl: `${iconRoot}/classicon_warlock.jpg`,
  },
  {
    slug: "warrior",
    englishName: "Warrior",
    colorClass: "[--class-color:#c69b6d]",
    iconUrl: `${iconRoot}/classicon_warrior.jpg`,
  },
];

export function getWowClass(slug: ClassSlug): WowClass {
  const wowClass = wowClasses.find((item) => item.slug === slug);

  if (!wowClass) {
    throw new Error(`Unknown WoW class: ${slug}`);
  }

  return wowClass;
}
