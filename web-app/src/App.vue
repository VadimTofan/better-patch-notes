<script setup lang="ts">
import { computed, provide, ref, watch } from "vue";
import { RouterView } from "vue-router";

import { localeKey } from "@/composables/useLocale";
import { getInitialLocale, persistLocale } from "@/domain/locale";
import { supportedLocales, type SupportedLocale } from "@/domain/locale.type";
import { localeNames, messages } from "@/i18n/messages";

const locale = ref<SupportedLocale>(getInitialLocale());
const text = computed(() => messages[locale.value]);

function setLocale(nextLocale: SupportedLocale): void {
  locale.value = nextLocale;
  persistLocale(nextLocale);
}

watch(
  locale,
  (nextLocale) => {
    document.documentElement.lang =
      nextLocale === "en"
        ? "en"
        : `${nextLocale.slice(0, 2)}-${nextLocale.slice(2)}`;
  },
  { immediate: true },
);

provide(localeKey, { locale, setLocale });
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <header class="border-b border-line bg-surface">
      <div
        class="mx-auto flex max-w-4xl items-center justify-between px-4 py-4"
      >
        <RouterLink class="flex items-center gap-3 text-text" to="/">
          <span
            class="grid size-8 place-items-center rounded-lg bg-blue-600 font-display font-bold"
            aria-hidden="true"
            >B</span
          >
          <span class="font-display font-semibold">{{ text.brand }}</span>
        </RouterLink>

        <label class="flex items-center gap-2">
          <span class="hidden text-muted sm:inline">{{
            text.chooseLanguage
          }}</span>
          <select
            class="rounded-lg border border-line bg-canvas px-3 py-2 text-text"
            data-testid="locale-select"
            :value="locale"
            @change="
              setLocale(
                ($event.target as HTMLSelectElement).value as SupportedLocale,
              )
            "
          >
            <option
              v-for="option in supportedLocales"
              :key="option"
              class="bg-canvas text-text"
              :value="option"
            >
              {{ localeNames[option] }}
            </option>
          </select>
        </label>
      </div>
    </header>

    <main class="mx-auto max-w-4xl flex-1 px-4 py-8">
      <RouterView />
    </main>

    <footer class="mx-auto max-w-4xl px-4 py-6 text-xs text-muted">
      <span class="font-semibold text-text-soft">Better Patch Notes</span>
      <span>
        — World of Warcraft® is a trademark of Blizzard Entertainment.</span
      >
    </footer>
  </div>
</template>
