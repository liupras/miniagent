import { createI18n } from "vue-i18n";
import { parse } from "yaml";
import zhCNRaw from "../locales/zh_CN.yaml?raw";
import enUSRaw from "../locales/en_US.yaml?raw";

export type AppLocale = "zh_CN" | "en_US";

export const LOCALE_STORAGE_KEY = "miniagent-workplace-locale";
export const DEFAULT_LOCALE: AppLocale = "zh_CN";

export function isAppLocale(value: unknown): value is AppLocale {
  return value === "zh_CN" || value === "en_US";
}

export function getSavedLocale(): AppLocale {
  const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
  return isAppLocale(saved) ? saved : DEFAULT_LOCALE;
}

export const i18n = createI18n({
  legacy: false,
  locale: getSavedLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages: {
    zh_CN: parse(zhCNRaw),
    en_US: parse(enUSRaw),
  },
});
