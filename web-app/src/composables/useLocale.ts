import type { InjectionKey, Ref } from "vue";
import { inject } from "vue";

import type { SupportedLocale } from "@/domain/locale.type";

export interface LocaleContext {
  locale: Ref<SupportedLocale>;
  setLocale: (locale: SupportedLocale) => void;
}

export const localeKey: InjectionKey<LocaleContext> = Symbol("locale");

export function useLocale(): LocaleContext {
  const context = inject(localeKey);

  if (!context) {
    throw new Error("Locale context is unavailable.");
  }

  return context;
}
