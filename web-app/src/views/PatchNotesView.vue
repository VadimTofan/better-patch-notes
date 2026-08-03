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
  <div class="notes" :style="{ '--class-color': selectedClass.color }">
    <section class="hero">
      <div class="hero__copy">
        <span class="hero__kicker">{{ text.updated }} {{ updatedDate }}</span>
        <h1 class="hero__title" data-testid="page-title">
          {{ selectedClassName }}
          <span class="hero__titleaccent">{{ text.classChanges }}</span>
        </h1>
        <p class="hero__tagline">{{ text.tagline }}</p>
      </div>

      <img
        class="hero__icon"
        :src="selectedClass.iconUrl"
        :alt="selectedClassName"
        width="96"
        height="96"
      />
    </section>

    <nav class="classrail" :aria-label="text.browseClasses">
      <span class="classrail__label">{{ text.browseClasses }}</span>
      <div class="classrail__list">
        <RouterLink
          v-for="wowClass in wowClasses"
          :key="wowClass.slug"
          class="classrail__link"
          :class="{
            'classrail__link--active': wowClass.slug === classSlug,
            'classrail__link--quiet': !classHasChanges(wowClass.englishName),
          }"
          data-testid="class-link"
          :to="`/${wowClass.slug}`"
          :title="localizedClassName(wowClass.englishName)"
          :aria-label="localizedClassName(wowClass.englishName)"
        >
          <img
            class="classrail__icon"
            :src="wowClass.iconUrl"
            alt=""
            width="40"
            height="40"
          />
        </RouterLink>
      </div>
    </nav>

    <div class="channels" role="tablist" aria-label="Patch-note channel">
      <button
        class="channels__button"
        :class="{ 'channels__button--active': channel === 'live' }"
        data-testid="channel-live"
        role="tab"
        type="button"
        :aria-selected="channel === 'live'"
        @click="channel = 'live'"
      >
        <span
          class="channels__status channels__status--live"
          aria-hidden="true"
        ></span>
        {{ text.live }}
      </button>
      <button
        class="channels__button"
        :class="{ 'channels__button--active': channel === 'ptr' }"
        data-testid="channel-ptr"
        role="tab"
        type="button"
        :aria-selected="channel === 'ptr'"
        @click="channel = 'ptr'"
      >
        <span
          class="channels__status channels__status--ptr"
          aria-hidden="true"
        ></span>
        {{ text.ptr }}
      </button>
    </div>

    <div class="notes__sections">
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

<style scoped lang="scss">
@use "@/styles/tokens" as *;

.notes {
  display: grid;
  gap: 1.25rem;
}

.hero {
  position: relative;
  display: flex;
  overflow: hidden;
  align-items: center;
  justify-content: space-between;
  min-height: 14rem;
  padding: 2.5rem;
  border: 0.0625rem solid $line;
  border-radius: 1.25rem;
  background:
    radial-gradient(
      circle at 85% 50%,
      color-mix(in srgb, var(--class-color) 24%, transparent),
      transparent 28%
    ),
    linear-gradient(135deg, $surface-raised, $surface);
}

.hero::after {
  position: absolute;
  right: -4rem;
  bottom: -7rem;
  width: 18rem;
  height: 18rem;
  border: 0.0625rem solid
    color-mix(in srgb, var(--class-color) 30%, transparent);
  border-radius: 50%;
  content: "";
}

.hero__copy {
  position: relative;
  z-index: 1;
}

.hero__kicker {
  color: $muted;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.hero__title {
  max-width: 44rem;
  margin: 0.75rem 0 0;
  font-family: $font-display;
  font-size: clamp(2.25rem, 6vw, 4.75rem);
  line-height: 0.98;
  letter-spacing: -0.055em;
}

.hero__titleaccent {
  display: block;
  color: var(--class-color);
}

.hero__tagline {
  max-width: 32rem;
  margin: 1.25rem 0 0;
  color: $text-soft;
  font-size: 1rem;
}

.hero__icon {
  position: relative;
  z-index: 1;
  width: 6rem;
  height: 6rem;
  border: 0.0625rem solid color-mix(in srgb, var(--class-color) 55%, $line);
  border-radius: 1.25rem;
  box-shadow: 0 0 3rem color-mix(in srgb, var(--class-color) 25%, transparent);
}

.classrail {
  padding: 1rem;
  border: 0.0625rem solid $line;
  border-radius: 1rem;
  background: $surface;
}

.classrail__label {
  display: block;
  margin: 0 0 0.75rem 0.25rem;
  color: $muted;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.classrail__list {
  display: grid;
  grid-template-columns: repeat(13, minmax(2.5rem, 1fr));
  gap: 0.5rem;
}

.classrail__link {
  display: grid;
  aspect-ratio: 1;
  place-items: center;
  border: 0.0625rem solid $line;
  border-radius: 0.625rem;
  background: $surface-raised;
  transition:
    border-color 140ms ease,
    opacity 140ms ease,
    transform 140ms ease;
}

.classrail__link:hover,
.classrail__link:focus-visible {
  border-color: $text-soft;
  transform: translateY(-0.125rem);
}

.classrail__link--active {
  border-color: var(--class-color);
  box-shadow: inset 0 0 0 0.0625rem var(--class-color);
}

.classrail__link--quiet {
  opacity: 0.42;
}

.classrail__link--active.classrail__link--quiet,
.classrail__link--quiet:hover,
.classrail__link--quiet:focus-visible {
  opacity: 1;
}

.classrail__icon {
  width: min(2.5rem, 76%);
  height: min(2.5rem, 76%);
  border-radius: 0.375rem;
}

.channels {
  display: inline-flex;
  width: fit-content;
  padding: 0.25rem;
  border: 0.0625rem solid $line;
  border-radius: 0.75rem;
  background: $surface;
  gap: 0.25rem;
}

.channels__button {
  display: inline-flex;
  align-items: center;
  min-height: 2.5rem;
  padding: 0 1rem;
  border: 0;
  border-radius: 0.5rem;
  background: transparent;
  color: $muted;
  cursor: pointer;
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 600;
  gap: 0.5rem;
}

.channels__button--active {
  background: $surface-raised;
  color: $text;
  box-shadow: 0 0.25rem 1rem rgb(0 0 0 / 18%);
}

.channels__status {
  width: 0.4375rem;
  height: 0.4375rem;
  border-radius: 50%;
}

.channels__status--live {
  background: $success;
  box-shadow: 0 0 0.75rem $success;
}

.channels__status--ptr {
  background: $warning;
  box-shadow: 0 0 0.75rem $warning;
}

.notes__sections {
  display: grid;
  gap: 0.75rem;
}

@media (max-width: 54rem) {
  .classrail__list {
    overflow-x: auto;
    grid-template-columns: repeat(13, 3rem);
    padding-bottom: 0.25rem;
  }
}

@media (max-width: 42rem) {
  .notes {
    gap: 1rem;
  }

  .hero {
    align-items: flex-start;
    min-height: 10.5rem;
    padding: 1.25rem;
  }

  .hero__copy {
    padding-right: 3.75rem;
  }

  .hero__title {
    margin-top: 0.625rem;
    font-size: clamp(1.85rem, 10vw, 2.75rem);
    line-height: 1.05;
  }

  .hero__tagline {
    margin-top: 1rem;
    font-size: 0.875rem;
  }

  .hero__icon {
    position: absolute;
    top: 1.25rem;
    right: 1.25rem;
    width: 3rem;
    height: 3rem;
    border-radius: 0.75rem;
    opacity: 0.8;
  }

  .classrail {
    padding: 0.75rem;
  }

  .classrail__label {
    margin-bottom: 0.625rem;
  }

  .classrail__list {
    overflow-x: visible;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    padding-bottom: 0;
    gap: 0.625rem;
  }

  .classrail__link {
    min-height: 3.25rem;
  }

  .channels {
    width: 100%;
  }

  .channels__button {
    justify-content: center;
    min-height: 2.75rem;
    flex: 1;
  }
}

@media (prefers-reduced-motion: reduce) {
  .classrail__link {
    transition: none;
  }
}
</style>
