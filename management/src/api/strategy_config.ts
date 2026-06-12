import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

// ──────────────────────────────────────────────
// 1. 类型定义 (对应后端 StrategyConfig 模式)
// ──────────────────────────────────────────────

export interface StrategyConfig {
  config_id: string;
  kb_id: number;
  version: number;
  is_active?: boolean;
  prompt_language?: string;
  // 组件开关
  enable_query_rewrite: boolean;
  enable_query_expansion: boolean;
  enable_query_hyde: boolean;
  enable_vector: boolean;
  enable_bm25: boolean;
  enable_reranker: boolean;
  enable_small_to_big: boolean;
  require_citation: boolean;
  // 检索参数
  query_expansion_num: number;
  max_transform_queries: number;
  vector_top_k: number;
  bm25_top_k: number;
  rrf_mode: string;
  rrf_k: number;
  rrf_top_k: number;
  vector_weight: number;
  reranking_mode: string;
  rerank_top_k: number;
  final_top_k: number;
  // 阈值参数
  vector_score_threshold: number;
  bm25_score_threshold: number;
  confidence_high_score_threshold: number;
  confidence_min_high_conf_count: number;
  confidence_low_score_threshold: number;
  // 其他
  extra_config?: Record<string, any>;
  created_at?: string;
  created_by?: string;
}

export interface KnowledgeBaseOption {
  id: number;
  name: string;
}

export type StrategyConfigCreate = StrategyConfig;
export type StrategyConfigUpdate = Partial<StrategyConfig>;

// ──────────────────────────────────────────────
// 2. API 接口定义
// ──────────────────────────────────────────────

/** 获取所有知识库选项 */
export const getKnowledgeBaseOptions = () => {
  return http.request<KnowledgeBaseOption[]>(
    "get",
    baseUrlApi("admin/knowledge-bases/options")
  );
};

/** 获取知识库下的策略列表 (带分页) */
export const getStrategyList = (
  kb_id?: number | null,
  params?: { page?: number; page_size?: number }
) => {
  return http.request<{
    total: number;
    items: StrategyConfig[];
  }>("get", baseUrlApi("admin/strategy-configs"), {
    params: {
      kb_id: kb_id ?? undefined,
      ...params
    }
  });
};

/** 获取单个策略详情 */
export const getStrategyDetail = (config_id: string) => {
  return http.request("get", baseUrlApi(`admin/strategy-configs/${config_id}`));
};

/** 获取知识库当前的激活策略 */
export const getActiveStrategy = (kb_id: number) => {
  return http.request(
    "get",
    baseUrlApi(`admin/strategy-configs/kb/${kb_id}/active`)
  );
};

/** 创建新策略 */
export const createStrategy = (data: StrategyConfigCreate) => {
  return http.request("post", baseUrlApi("admin/strategy-configs"), { data });
};

/** 部分更新策略 */
export const updateStrategy = (
  config_id: string,
  data: StrategyConfigUpdate
) => {
  return http.request(
    "patch",
    baseUrlApi(`admin/strategy-configs/${config_id}`),
    {
      data
    }
  );
};

/** 激活策略 (会自动停用该 KB 下的其他策略) */
export const activateStrategy = (config_id: string) => {
  return http.request(
    "post",
    baseUrlApi(`admin/strategy-configs/${config_id}/activate`)
  );
};

/** 删除策略 */
export const deleteStrategy = (config_id: string) => {
  return http.request(
    "delete",
    baseUrlApi(`admin/strategy-configs/${config_id}`)
  );
};
