import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export type LoginEventType = "LOGIN" | "REFRESH_TOKEN";

export interface LoginLogItem {
  id: number;
  request_id: string;
  event_type: LoginEventType;
  user_id?: number | null;
  username?: string | null;
  ip_address?: string | null;
  user_agent?: string | null;
  success: boolean;
  failure_reason?: string | null;
  created_at: string;
}

export interface LoginLogListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  request_id?: string;
  user_id?: number;
  username?: string;
  ip_address?: string;
  event_type?: LoginEventType;
  success?: boolean;
  created_from?: string;
  created_to?: string;
}

export interface LoginLogPageResult {
  total: number;
  page: number;
  page_size: number;
  data: LoginLogItem[];
}

const BASE_URL = "admin/login-logs";

export const getLoginLogList = (params: LoginLogListParams) =>
  http.request<LoginLogPageResult>("get", baseUrlApi(BASE_URL), { params });

export const getLoginLog = (loginLogId: number) =>
  http.request<LoginLogItem>("get", baseUrlApi(`${BASE_URL}/${loginLogId}`));
