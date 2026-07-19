import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export type SystemSettingValueType =
  | "string"
  | "int"
  | "float"
  | "bool"
  | "json";

export interface SystemSettingItem {
  key: string;
  value: string;
  value_type: SystemSettingValueType;
  group: string;
  description?: string | null;
  is_readonly: boolean;
  updated_at?: string | null;
}

const BASE_URL = "admin/system-settings";

export const getSystemSettings = (group?: string) =>
  http.request<SystemSettingItem[]>("get", baseUrlApi(BASE_URL), {
    params: group ? { group } : undefined
  });

export const updateSystemSetting = (key: string, value: string) =>
  http.request<SystemSettingItem>(
    "patch",
    baseUrlApi(`${BASE_URL}/${encodeURIComponent(key)}`),
    { data: { value } }
  );
