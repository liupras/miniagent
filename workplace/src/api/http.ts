import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { RefreshResponse } from "../types/auth";
import { clearSession, getSession, saveSession } from "../utils/session";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
});

let refreshPromise: Promise<string> | null = null;

export async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const session = getSession();
    if (!session?.refreshToken) throw new Error("Missing refresh token");

    const response = await axios.post<RefreshResponse>(
      `${API_BASE_URL}/api/v1/refresh-token`,
      { refreshToken: session.refreshToken },
      { timeout: 15_000 },
    );
    if (!response.data.success || !response.data.data) {
      throw new Error(response.data.message || "登录状态已失效");
    }

    saveSession({ ...session, ...response.data.data });
    return response.data.data.accessToken;
  })()
    .catch((error) => {
      clearSession();
      throw error;
    })
    .finally(() => {
      refreshPromise = null;
    });

  return refreshPromise;
}

http.interceptors.request.use((config) => {
  const token = getSession()?.accessToken;
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

interface RetryableRequest extends InternalAxiosRequestConfig {
  _retried?: boolean;
}

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config as RetryableRequest | undefined;
    const isAuthRequest = request?.url?.includes("/api/v1/login");
    const isRefreshRequest = request?.url?.includes("/api/v1/refresh-token");

    if (
      error.response?.status === 401 &&
      request &&
      !request._retried &&
      !isAuthRequest &&
      !isRefreshRequest
    ) {
      request._retried = true;
      try {
        request.headers.Authorization = `Bearer ${await refreshAccessToken()}`;
        return http(request);
      } catch {
        window.location.hash = "#/login";
      }
    }

    return Promise.reject(error);
  },
);
