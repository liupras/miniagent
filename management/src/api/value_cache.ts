import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

/** 单个命名空间的统计信息，对应后端 CacheStoreStatsItem */
export interface CacheStoreStatsItem {
  namespace: string;
  backend_type: string;
  size?: number;
  backend_stats?: Record<string, any>;
  sample_keys?: string[];
}

export interface CacheStoreKeysResult {
  namespace: string;
  keys: string[];
  prefix?: string;
  limit: number;
  truncated: boolean;
}

export interface CacheStoreDeleteKeysResult {
  namespace: string;
  deleted_count: number;
}

export interface CacheStoreClearResult {
  namespace: string;
  cleared_count: number;
}

export interface CacheStoreClearAllResult {
  results: Record<string, number>;
}

/** 获取所有已注册的命名空间列表 */
export const getCacheStoreNamespaces = () => {
  return http.request<string[]>("get", baseUrlApi("admin/value-cache/list"));
};

/** 获取命名空间统计信息；不传 namespace 时返回全部 */
export const getCacheStoreStats = (namespace?: string) => {
  return http.request<Record<string, CacheStoreStatsItem>>(
    "get",
    baseUrlApi("admin/value-cache/stats"),
    { params: namespace ? { namespace } : {} }
  );
};

/** 按前缀查询指定命名空间下的 key 列表 */
export const getCacheStoreKeys = (
  namespace: string,
  params?: { prefix?: string; limit?: number }
) => {
  return http.request<CacheStoreKeysResult>(
    "get",
    baseUrlApi(`admin/value-cache/${namespace}/keys`),
    { params }
  );
};

/** 删除指定命名空间下的若干 key */
export const deleteCacheStoreKeys = (namespace: string, keys: string[]) => {
  return http.request<CacheStoreDeleteKeysResult>(
    "post",
    baseUrlApi(`admin/value-cache/${namespace}/delete-keys`),
    { data: { keys } }
  );
};

/** 清空指定命名空间 */
export const clearCacheStoreNamespace = (namespace: string) => {
  return http.request<CacheStoreClearResult>(
    "post",
    baseUrlApi(`admin/value-cache/${namespace}/clear`)
  );
};

/** 清空所有命名空间 */
export const clearAllCacheStoreNamespaces = () => {
  return http.request<CacheStoreClearAllResult>(
    "post",
    baseUrlApi("admin/value-cache/clear-all")
  );
};
