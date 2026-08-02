import { getWowClass } from "./classes";
import type { ClassSlug } from "./classes.type";
import type { SupportedLocale } from "./locale.type";
import type {
  LocalizedRecord,
  PatchChannel,
  PatchNoteRecord,
  VisiblePatchNotes,
} from "./patchNotes.type";

export function localizeRecord(
  record: PatchNoteRecord,
  locale: SupportedLocale,
): LocalizedRecord {
  const localizedContent = record.localizations[locale];

  return {
    record,
    content: localizedContent ?? record.localizations.en,
    usedFallback: localizedContent === undefined,
  };
}

export function getVisiblePatchNotes(
  records: readonly PatchNoteRecord[],
  classSlug: ClassSlug,
  channel: PatchChannel,
): VisiblePatchNotes {
  const selectedClass = getWowClass(classSlug);
  const channelRecords = records.filter((record) => record.channel === channel);

  return {
    classNotes: channelRecords.filter(
      (record) =>
        record.category === "Class" &&
        record.localizations.en.name === selectedClass.englishName,
    ),
    dungeonNotes: channelRecords.filter(
      (record) => record.category === "Dungeon",
    ),
    raidNotes: channelRecords.filter((record) => record.category === "Raid"),
  };
}
