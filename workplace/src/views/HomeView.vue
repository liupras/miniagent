<script setup lang="ts">
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";
import {
  themeOptions,
  usePreferencesStore,
  type ThemeTone,
} from "../stores/preferences";
import type { AppLocale } from "../i18n";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const preferences = usePreferencesStore();
const languageOptions: AppLocale[] = ["zh_CN", "en_US"];

function changeLanguage(event: Event) {
  preferences.setLanguage(
    (event.target as HTMLSelectElement).value as AppLocale,
  );
}

function changeTheme(theme: ThemeTone) {
  preferences.setTheme(theme);
}

async function logout() {
  auth.logout();
  await router.replace({ name: "login" });
}
</script>

<template>
  <div class="home-page">
    <header class="home-header">
      <a class="home-logo" href="#/" :aria-label="t('home.logoLabel')">
        <img src="/logo.svg" alt="" />
        <span>MiniAgent</span>
        <small>Workplace</small>
      </a>

      <div class="header-tools">
        <label class="language-control">
          <span>{{ t("common.language") }}</span>
          <select :value="preferences.language" @change="changeLanguage">
            <option
              v-for="locale in languageOptions"
              :key="locale"
              :value="locale"
            >
              {{ t(`languages.${locale}`) }}
            </option>
          </select>
        </label>

        <div class="theme-control" :aria-label="t('common.theme')">
          <span>{{ t("common.theme") }}</span>
          <div class="theme-options">
            <button
              v-for="option in themeOptions"
              :key="option.value"
              type="button"
              class="theme-swatch"
              :class="{ active: preferences.theme === option.value }"
              :style="{ '--swatch-color': option.color }"
              :title="t(`themes.${option.value}`)"
              :aria-label="t(`themes.${option.value}`)"
              :aria-pressed="preferences.theme === option.value"
              @click="changeTheme(option.value)"
            />
          </div>
        </div>

        <div class="user-actions">
          <el-avatar :src="auth.session?.avatar || undefined" :size="34">
            {{ auth.displayName.slice(0, 1).toUpperCase() }}
          </el-avatar>
          <span class="user-name">{{ auth.displayName }}</span>
          <el-button text @click="logout">{{ t("common.logout") }}</el-button>
        </div>
      </div>
    </header>
    <main class="home-content" :aria-label="t('home.contentLabel')" />
  </div>
</template>
