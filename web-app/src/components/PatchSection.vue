<script setup lang="ts">
import { computed } from "vue";

import type { SupportedLocale } from "@/domain/locale.type";
import { localizeRecord } from "@/domain/patchNotes";
import type { PatchNoteRecord } from "@/domain/patchNotes.type";
import { messages } from "@/i18n/messages";

const props = defineProps<{
  title: string;
  notes: readonly PatchNoteRecord[];
  locale: SupportedLocale;
  expanded?: boolean;
}>();

const localizedNotes = computed(() =>
  props.notes.map((note) => localizeRecord(note, props.locale)),
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
  <details class="section" :open="expanded">
    <summary class="section__summary">
      <span class="section__heading">{{ title }}</span>
      <span class="section__count">{{ notes.length }}</span>
      <span class="section__chevron" aria-hidden="true">⌄</span>
    </summary>

    <div class="section__content">
      <p v-if="localizedNotes.length === 0" class="empty">
        {{ text.noChanges }}
      </p>

      <article
        v-for="note in localizedNotes"
        :key="note.record.id"
        class="card"
      >
        <div class="card__header">
          <div class="card__identity">
            <span v-if="note.content.specialization" class="card__eyebrow">
              {{ note.content.specialization }}
            </span>
            <h3 class="card__title">{{ note.content.name }}</h3>
          </div>

          <div class="card__meta">
            <span class="card__patch"
              >{{ text.patch }} {{ note.record.patch }}</span
            >
            <time class="card__date" :datetime="note.record.date">
              {{ formatDate(note.record.date) }}
            </time>
          </div>
        </div>

        <ul class="card__changes">
          <li
            v-for="change in note.content.change"
            :key="change"
            class="card__change"
          >
            {{ change }}
          </li>
        </ul>

        <span v-if="note.usedFallback" class="card__fallback">
          {{ text.englishFallback }}
        </span>
      </article>
    </div>
  </details>
</template>

<style scoped lang="scss">
@use "@/styles/tokens" as *;

.section {
  overflow: hidden;
  border: 0.0625rem solid $line;
  border-radius: 1rem;
  background: $surface;
  box-shadow: 0 1.5rem 4rem rgb(0 0 0 / 18%);
}

.section__summary {
  display: flex;
  align-items: center;
  min-height: 4.5rem;
  padding: 1rem 1.25rem;
  cursor: pointer;
  list-style: none;
  gap: 0.75rem;
}

.section__summary::-webkit-details-marker {
  display: none;
}

.section__heading {
  flex: 1;
  font-family: $font-display;
  font-size: 1rem;
  font-weight: 600;
}

.section__count {
  min-width: 2rem;
  padding: 0.25rem 0.5rem;
  border: 0.0625rem solid $line;
  border-radius: 999rem;
  color: $muted;
  font-size: 0.75rem;
  text-align: center;
}

.section__chevron {
  color: $muted;
  transition: transform 160ms ease;
}

.section[open] .section__chevron {
  transform: rotate(180deg);
}

.section__content {
  display: grid;
  padding: 0 1rem 1rem;
  gap: 0.75rem;
}

.card {
  padding: 1.25rem;
  border: 0.0625rem solid $line-soft;
  border-radius: 0.75rem;
  background: $surface-raised;
}

.card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.card__identity {
  min-width: 0;
}

.card__eyebrow {
  color: var(--class-color, $accent);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.card__title {
  margin: 0.25rem 0 0;
  font-family: $font-display;
  font-size: 1rem;
}

.card__meta {
  display: flex;
  flex-shrink: 0;
  align-items: flex-end;
  color: $muted;
  font-size: 0.6875rem;
  flex-direction: column;
  gap: 0.25rem;
}

.card__patch {
  color: $text-soft;
}

.card__changes {
  display: grid;
  margin: 1rem 0 0;
  padding: 0 0 0 1.125rem;
  color: $text-soft;
  gap: 0.625rem;
}

.card__change {
  padding-left: 0.25rem;
  line-height: 1.65;
}

.card__change::marker {
  color: var(--class-color, $accent);
}

.card__fallback {
  display: inline-flex;
  margin-top: 1rem;
  padding: 0.25rem 0.5rem;
  border-radius: 0.375rem;
  background: $warning-soft;
  color: $warning;
  font-size: 0.6875rem;
}

.empty {
  margin: 0;
  padding: 1.25rem;
  border: 0.0625rem dashed $line;
  border-radius: 0.75rem;
  color: $muted;
  text-align: center;
}

@media (max-width: 42rem) {
  .section__summary {
    min-height: 4rem;
    padding: 0.875rem 1rem;
  }

  .section__content {
    padding: 0 0.75rem 0.75rem;
  }

  .card {
    padding: 1rem;
  }

  .card__header {
    flex-direction: column;
    gap: 0.75rem;
  }

  .card__meta {
    flex-wrap: wrap;
    align-items: flex-start;
    flex-direction: row;
  }

  .card__changes {
    margin-top: 0.875rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  .section__chevron {
    transition: none;
  }
}
</style>
