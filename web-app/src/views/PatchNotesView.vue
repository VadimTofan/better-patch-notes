<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute } from "vue-router";

import PatchSection from "@/components/PatchSection.vue";
import { useLocale } from "@/composables/useLocale";
import { getWowClass, wowClasses } from "@/domain/classes";
import type { ClassSlug } from "@/domain/classes.type";
import { getVisiblePatchNotes, localizeRecord } from "@/domain/patchNotes";
import type { PatchChannel, PatchNotesData } from "@/domain/patchNotes.type";
import { messages } from "@/i18n/messages";
import patchNotesJson from "@/generated/patch-notes.json";

const patchNotes = patchNotesJson as PatchNotesData;
const route = useRoute();
const { locale } = useLocale();
const channel = ref<PatchChannel>("live");

const classSlug = computed(() => route.params.classSlug as ClassSlug);
const selectedClass = computed(() => getWowClass(classSlug.value));
const text = computed(() => messages[locale.value]);
const visibleNotes = computed(() =>
  getVisiblePatchNotes(patchNotes.changes, classSlug.value, channel.value),
);

const selectedClassName = computed(() => {
  const sourceRecord = patchNotes.changes.find(
    (record) =>
      record.category === "Class" &&
      record.localizations.en.name === selectedClass.value.englishName,
  );

  return sourceRecord
    ? localizeRecord(sourceRecord, locale.value).content.name
    : selectedClass.value.englishName;
});

const updatedDate = computed(() =>
  new Intl.DateTimeFormat(
    locale.value === "en"
      ? "en-US"
      : `${locale.value.slice(0, 2)}-${locale.value.slice(2)}`,
    { day: "numeric", month: "long", year: "numeric" },
  ).format(new Date(patchNotes.updatedAt)),
);

function localizedClassName(englishName: string): string {
  const sourceRecord = patchNotes.changes.find(
    (record) =>
      record.category === "Class" &&
      record.localizations.en.name === englishName,
  );

  return sourceRecord
    ? localizeRecord(sourceRecord, locale.value).content.name
    : englishName;
}

function classHasChanges(englishName: string): boolean {
  return patchNotes.changes.some(
    (record) =>
      record.channel === channel.value &&
      record.category === "Class" &&
      record.localizations.en.name === englishName,
  );
}

watch(
  classSlug,
  (nextClass) => {
    localStorage.setItem("bpn_last_class", nextClass);
  },
  { immediate: true },
);
</script>

<template>
  <div class="grid gap-6" :class="selectedClass.colorClass">
    <section
      class="flex items-center justify-between gap-4 border-b border-line pb-6"
    >
      <div>
        <span class="text-xs font-semibold tracking-wide text-muted uppercase">
          {{ text.updated }} {{ updatedDate }}
        </span>
        <h1
          class="mt-2 font-display text-3xl font-bold sm:text-4xl"
          data-testid="page-title"
        >
          {{ selectedClassName }}
          <span class="text-[var(--class-color)]">{{ text.classChanges }}</span>
        </h1>
        <p class="mt-2 text-text-soft">{{ text.tagline }}</p>
      </div>

      <img
        class="size-16 rounded-xl"
        :src="selectedClass.iconUrl"
        :alt="selectedClassName"
        width="64"
        height="64"
      />
    </section>

    <nav :aria-label="text.browseClasses">
      <span class="mb-2 block text-xs font-semibold text-muted uppercase">
        {{ text.browseClasses }}
      </span>
      <div class="grid grid-cols-4 gap-2 sm:grid-cols-7 lg:grid-cols-13">
        <RouterLink
          v-for="wowClass in wowClasses"
          :key="wowClass.slug"
          class="aspect-square rounded-lg bg-surface-raised p-2 opacity-50 hover:opacity-100"
          :class="{
            'opacity-100 ring-2 ring-[var(--class-color)]':
              wowClass.slug === classSlug,
            'opacity-100': classHasChanges(wowClass.englishName),
          }"
          data-testid="class-link"
          :to="`/${wowClass.slug}`"
          :title="localizedClassName(wowClass.englishName)"
          :aria-label="localizedClassName(wowClass.englishName)"
        >
          <img
            class="size-full rounded-md"
            :src="wowClass.iconUrl"
            alt=""
            width="40"
            height="40"
          />
        </RouterLink>
      </div>
    </nav>

    <div class="flex gap-2" role="tablist" aria-label="Patch-note channel">
      <button
        class="rounded-lg px-4 py-2 font-semibold text-muted"
        :class="{ 'bg-surface-raised text-text': channel === 'live' }"
        data-testid="channel-live"
        role="tab"
        type="button"
        :aria-selected="channel === 'live'"
        @click="channel = 'live'"
      >
        {{ text.live }}
      </button>
      <button
        class="rounded-lg px-4 py-2 font-semibold text-muted"
        :class="{ 'bg-surface-raised text-text': channel === 'ptr' }"
        data-testid="channel-ptr"
        role="tab"
        type="button"
        :aria-selected="channel === 'ptr'"
        @click="channel = 'ptr'"
      >
        {{ text.ptr }}
      </button>
    </div>

    <div class="grid gap-3">
      <PatchSection
        :title="text.classChanges"
        :notes="visibleNotes.classNotes"
        :locale="locale"
        expanded
      />
      <PatchSection
        :title="text.dungeonChanges"
        :notes="visibleNotes.dungeonNotes"
        :locale="locale"
        expanded
      />
      <PatchSection
        :title="text.raidChanges"
        :notes="visibleNotes.raidNotes"
        :locale="locale"
      />
    </div>
  </div>
</template>
