import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export type AuditAction = "CREATE" | "UPDATE" | "DELETE" | "EXECUTE";
export type AuditStatus = "success" | "failure";

export interface AuditLogItem {
  id: number;
  request_id: string;
  user_id?: number | null;
  username?: string | null;
  ip_address?: string | null;
  target_type: string;
  target_id: string;
  action: AuditAction;
  before_value?: unknown | null;
  after_value?: unknown | null;
  description?: string | null;
  status: AuditStatus;
  created_at: string;
}

export interface AuditLogListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  request_id?: string;
  user_id?: number;
  username?: string;
  target_type?: string;
  target_id?: string;
  action?: AuditAction;
  status?: AuditStatus;
  created_from?: string;
  created_to?: string;
}

export interface AuditLogPageResult {
  total: number;
  page: number;
  page_size: number;
  data: AuditLogItem[];
}

const BASE_URL = "admin/audit-logs";

export const getAuditLogList = (params: AuditLogListParams) =>
  http.request<AuditLogPageResult>("get", baseUrlApi(BASE_URL), { params });

export const getAuditLog = (auditId: number) =>
  http.request<AuditLogItem>("get", baseUrlApi(`${BASE_URL}/${auditId}`));
