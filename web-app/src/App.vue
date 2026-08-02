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
  <div class="shell">
    <header class="topbar">
      <RouterLink class="topbar__brand" to="/">
        <span class="topbar__mark" aria-hidden="true">B</span>
        <span class="topbar__wordmark">{{ text.brand }}</span>
      </RouterLink>

      <label class="locale">
        <span class="locale__label">{{ text.chooseLanguage }}</span>
        <select
          class="locale__select"
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
            class="locale__option"
            :value="option"
          >
            {{ localeNames[option] }}
          </option>
        </select>
      </label>
    </header>

    <main class="shell__content">
      <RouterView />
    </main>

    <footer class="footer">
      <span class="footer__brand">Better Patch Notes</span>
      <span class="footer__note"
        >World of Warcraft® is a trademark of Blizzard Entertainment.</span
      >
    </footer>
  </div>
</template>
