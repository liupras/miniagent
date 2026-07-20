import { computed, onScopeDispose, ref } from "vue";
import { defineStore } from "pinia";
import { loginApi } from "../api/auth";
import { refreshAccessToken } from "../api/http";
import type { AuthSession } from "../types/auth";
import {
  clearSession,
  getExpiresAt,
  getSession,
  saveSession,
} from "../utils/session";

const REFRESH_AHEAD_MS = 60_000;

export class AuthenticationError extends Error {
  readonly code?: string | null;

  constructor(message: string, code?: string | null) {
    super(message);
    this.name = "AuthenticationError";
    this.code = code;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const session = ref<AuthSession | null>(getSession());
  const isAuthenticated = computed(() => Boolean(session.value?.accessToken));
  const displayName = computed(
    () => session.value?.nickname || session.value?.username || "用户",
  );
  let refreshTimer: number | undefined;

  function cancelRefreshTimer() {
    if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
    refreshTimer = undefined;
  }

  async function refresh() {
    try {
      await refreshAccessToken();
      session.value = getSession();
      scheduleRefresh();
      return true;
    } catch {
      logout();
      window.location.hash = "#/login";
      return false;
    }
  }

  function scheduleRefresh() {
    cancelRefreshTimer();
    if (!session.value) return;
    const delay = Math.max(
      0,
      getExpiresAt(session.value.expires) - Date.now() - REFRESH_AHEAD_MS,
    );
    refreshTimer = window.setTimeout(() => void refresh(), delay);
  }

  async function login(username: string, password: string) {
    const result = await loginApi(username, password);
    if (!result.success || !result.data) {
      throw new AuthenticationError(
        result.message || "Authentication failed",
        result.error_code,
      );
    }
    session.value = result.data;
    saveSession(result.data);
    scheduleRefresh();
  }

  function logout() {
    cancelRefreshTimer();
    clearSession();
    session.value = null;
  }

  function initialize() {
    session.value = getSession();
    if (!session.value) return;
    if (getExpiresAt(session.value.expires) <= Date.now() + REFRESH_AHEAD_MS) {
      void refresh();
    } else {
      scheduleRefresh();
    }
  }

  onScopeDispose(cancelRefreshTimer);

  return {
    session,
    isAuthenticated,
    displayName,
    initialize,
    login,
    refresh,
    logout,
  };
});
