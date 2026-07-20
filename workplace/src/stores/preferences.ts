import { ref } from "vue";
import { defineStore } from "pinia";
import {
  getSavedLocale,
  i18n,
  isAppLocale,
  LOCALE_STORAGE_KEY,
  type AppLocale,
} from "../i18n";

export type ThemeTone = "ocean" | "violet" | "emerald" | "sunset";

const THEME_STORAGE_KEY = "miniagent-workplace-theme";
const DEFAULT_THEME: ThemeTone = "ocean";

export const themeOptions: Array<{ value: ThemeTone; color: string }> = [
  { value: "ocean", color: "#1769c2" },
  { value: "violet", color: "#7656c9" },
  { value: "emerald", color: "#16836b" },
  { value: "sunset", color: "#d5653f" },
];

function isThemeTone(value: unknown): value is ThemeTone {
  return themeOptions.some((option) => option.value === value);
}

function getSavedTheme(): ThemeTone {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  return isThemeTone(saved) ? saved : DEFAULT_THEME;
}

export const usePreferencesStore = defineStore("preferences", () => {
  const language = ref<AppLocale>(getSavedLocale());
  const theme = ref<ThemeTone>(getSavedTheme());

  function setLanguage(value: AppLocale) {
    if (!isAppLocale(value)) return;
    language.value = value;
    i18n.global.locale.value = value;
    localStorage.setItem(LOCALE_STORAGE_KEY, value);
    document.documentElement.lang = value === "zh_CN" ? "zh-CN" : "en-US";
  }

  function setTheme(value: ThemeTone) {
    if (!isThemeTone(value)) return;
    theme.value = value;
    localStorage.setItem(THEME_STORAGE_KEY, value);
    document.documentElement.dataset.theme = value;
  }

  function initialize() {
    setLanguage(language.value);
    setTheme(theme.value);
  }

  return { language, theme, initialize, setLanguage, setTheme };
});
