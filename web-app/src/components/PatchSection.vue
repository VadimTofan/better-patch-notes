<script setup lang="ts">
import { computed } from "vue";

import type { SupportedLocale } from "@/domain/locale.type";
import { getSafeSourceUrl, localizeRecord } from "@/domain/patchNotes";
import type { PatchNoteRecord } from "@/domain/patchNotes.type";
import { messages } from "@/i18n/messages";

const props = defineProps<{
  title: string;
  notes: readonly PatchNoteRecord[];
  locale: SupportedLocale;
  expanded?: boolean;
}>();

const localizedNotes = computed(() =>
  props.notes.map((note) => {
    const localizedNote = localizeRecord(note, props.locale);

    return {
      ...localizedNote,
      sourceUrl: getSafeSourceUrl(localizedNote.content.sourceUrl),
    };
  }),
);
const text = computed(() => messages[props.locale]);

function formatDate(date: string): string {
  const locale =
    props.locale === "en"
      ? "en-US"
      : `${props.locale.slice(0, 2)}-${props.locale.slice(2)}`;

  return new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T00:00:00Z`));
}
</script>

<template>
  <details
    class="group rounded-xl border border-line bg-surface"
    :open="expanded"
  >
    <summary class="flex list-none items-center gap-3 px-4 py-4">
      <span class="flex-1 font-display font-semibold">{{ title }}</span>
      <span class="rounded-full bg-surface-raised px-2 py-1 text-xs text-muted">
        {{ notes.length }}
      </span>
      <span class="text-muted group-open:rotate-180" aria-hidden="true">⌄</span>
    </summary>

    <div class="grid gap-3 px-3 pb-3">
      <p
        v-if="localizedNotes.length === 0"
        class="rounded-lg border border-dashed border-line p-4 text-center text-muted"
      >
        {{ text.noChanges }}
      </p>

      <article
        v-for="note in localizedNotes"
        :key="note.record.id"
        class="rounded-lg border border-line-soft bg-surface-raised p-4"
      >
        <div class="flex flex-col gap-2 sm:flex-row sm:justify-between">
          <div>
            <span
              v-if="note.content.specialization"
              class="text-xs font-semibold tracking-wide text-[var(--class-color)] uppercase"
            >
              {{ note.content.specialization }}
            </span>
            <h3 class="mt-1 font-display font-semibold">
              {{ note.content.name }}
            </h3>
          </div>

          <div class="flex gap-2 text-xs text-muted sm:flex-col sm:text-right">
            <span>{{ text.patch }} {{ note.record.patch }}</span>
            <time :datetime="note.record.date">
              {{ formatDate(note.record.date) }}
            </time>
          </div>
        </div>

        <ul class="mt-3 grid list-disc gap-2 pl-5 text-text-soft">
          <li
            v-for="change in note.content.change"
            :key="change"
            class="leading-relaxed marker:text-[var(--class-color)]"
          >
            {{ change }}
          </li>
        </ul>

        <footer
          v-if="note.usedFallback || note.sourceUrl"
          class="mt-4 flex flex-wrap items-center justify-between gap-3"
        >
          <span
            v-if="note.usedFallback"
            class="rounded bg-warning-soft px-2 py-1 text-xs text-warning"
          >
            {{ text.englishFallback }}
          </span>

          <a
            v-if="note.sourceUrl"
            class="rounded-lg border border-line px-3 py-2 text-text-soft"
            data-testid="source-link"
            :href="note.sourceUrl"
            target="_blank"
            rel="noopener noreferrer"
          >
            {{ text.source }}
            <span aria-hidden="true">↗</span>
          </a>
        </footer>
      </article>
    </div>
  </details>
</template>
