import type { SupportedLocale } from "./locale.type";

export type PatchChannel = "live" | "ptr";
export type PatchCategory = "Class" | "Dungeon" | "Raid";
export type TranslationType = "official" | "agent";

export interface LocalizedPatchNote {
  name: string;
  specialization: string;
  source: string;
  sourceUrl: string;
  translationType: TranslationType;
  translatedFrom: string;
  change: string[];
  terminologySourceUrls: string[];
}

export interface PatchNoteRecord {
  id: string;
  channel: PatchChannel;
  category: PatchCategory;
  date: string;
  patch: string;
  localizations: Partial<Record<SupportedLocale, LocalizedPatchNote>> & {
    en: LocalizedPatchNote;
  };
  retrievedAt: string;
}

export interface PatchNotesData {
  schemaVersion: 5;
  updatedAt: string;
  changes: PatchNoteRecord[];
}

export interface LocalizedRecord {
  record: PatchNoteRecord;
  content: LocalizedPatchNote;
  usedFallback: boolean;
}

export interface VisiblePatchNotes {
  classNotes: PatchNoteRecord[];
  dungeonNotes: PatchNoteRecord[];
  raidNotes: PatchNoteRecord[];
}
