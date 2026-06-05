import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export interface DomainItem {
  id?: number;
  name: string;
  type: string;
  processor_class: string;
  plugin_class: string;
  description?: string;
  metadata_schema?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

// 获取列表
export const getDomainList = (params?: object) => {
  return http.request("get", baseUrlApi("admin/domains"), { params });
};

// 创建
export const createDomain = (data: DomainItem) => {
  return http.request("post", baseUrlApi("admin/domains"), { data });
};

// 更新
export const updateDomain = (id: number, data: Partial<DomainItem>) => {
  return http.request("patch", baseUrlApi(`admin/domains/${id}`), { data });
};

// 删除
export const deleteDomain = (id: number) => {
  return http.request("delete", baseUrlApi(`admin/domains/${id}`));
};

// 批量删除
export const bulkDeleteDomains = (ids: number[]) => {
  return http.request("post", baseUrlApi("admin/domains/bulk-delete"), {
    data: ids
  });
};
