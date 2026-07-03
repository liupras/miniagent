import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

/** 单个缓存的统计信息，对应后端 CacheStatsItem */
export interface CacheStatsItem {
  name: string;
  size: number;
  keys: any[];
  description: string;
}

export interface CacheInvalidateResult {
  name: string;
  key: any;
  invalidated: boolean;
}

export interface CacheInvalidateAllResult {
  name: string;
  count: number;
}

export interface CacheInvalidateEverywhereResult {
  key: any;
  results: Record<string, boolean>;
}

/** 获取所有已注册缓存的名称列表 */
export const getCacheNames = () => {
  return http.request<string[]>("get", baseUrlApi("admin/object-cache/list"));
};

/** 获取缓存统计信息；不传 name 时返回全部缓存 */
export const getCacheStats = (name?: string) => {
  return http.request<Record<string, CacheStatsItem>>(
    "get",
    baseUrlApi("admin/object-cache/stats"),
    { params: name ? { name } : {} }
  );
};

/** 按 key 失效指定缓存中的一条记录 */
export const invalidateCacheKey = (name: string, key: any) => {
  return http.request<CacheInvalidateResult>(
    "post",
    baseUrlApi(`admin/object-cache/${name}/invalidate`),
    { data: { key } }
  );
};

/** 清空指定缓存的全部记录 */
export const invalidateCacheAll = (name: string) => {
  return http.request<CacheInvalidateAllResult>(
    "post",
    baseUrlApi(`admin/object-cache/${name}/invalidate-all`)
  );
};

/** 使用同一个原始 key，尝试让所有已注册缓存失效 */
export const invalidateCacheEverywhere = (key: any) => {
  return http.request<CacheInvalidateEverywhereResult>(
    "post",
    baseUrlApi("admin/object-cache/invalidate-everywhere"),
    { data: { key } }
  );
};
