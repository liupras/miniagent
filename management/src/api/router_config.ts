import { http } from "@/utils/http";
import { baseUrlApi } from "@/api/utils";

// ─── Response types ───────────────────────────────────────────────────────────

export interface RouterConfigItem {
  config_id: string;
  selection_strategy: "keyword" | "embedding";
  fallback_to_all: boolean;
  max_kb_count: number;
  extra_config: Record<string, unknown> | null;
  created_at: string;
}

export interface RouterConfigUpdatePayload {
  selection_strategy?: "keyword" | "embedding";
  fallback_to_all?: boolean;
  max_kb_count?: number;
  extra_config?: Record<string, unknown> | null;
}

export const getRouterConfigList = () =>
  http.request<RouterConfigItem[]>("get", baseUrlApi("admin/router-configs/"));

export const getRouterConfigById = (configId: string) =>
  http.request<{ data: RouterConfigItem }>(
    "get",
    baseUrlApi(`admin/router-configs/${configId}`)
  );

export const updateRouterConfig = (
  configId: string,
  payload: RouterConfigUpdatePayload
) =>
  http.request<{ data: null }>(
    "patch",
    baseUrlApi(`admin/router-configs/${configId}`),
    { data: payload }
  );
