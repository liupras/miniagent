import { http } from "@/utils/http";
import { baseUrlApi } from "@/api/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface KnowledgeBaseItem {
  id: number;
  name: string;
  domain_id: number;
  keywords: string[] | null;
  description: string | null;
  collection_name: string;
  embedding_id: number | null;
  chunk_size: number;
  chunk_overlap: number;
  parent_size: number;
  parent_overlap: number;
  llm_id: number | null;
  is_active: boolean;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseListResult {
  total: number;
  page: number;
  page_size: number;
  items: KnowledgeBaseItem[];
}

export interface KnowledgeBaseStats {
  id: number;
  name: string;
  document_count: number;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  is_active: boolean;
}

export interface KnowledgeBaseOption {
  id: number;
  name: string;
}

export interface KbListQuery {
  name?: string;
  domain_id?: number;
  is_active?: boolean;
  page: number;
  page_size: number;
}

export interface KbCreatePayload {
  name: string;
  domain_id: number;
  collection_name: string;
  keywords?: string[];
  description?: string;
  embedding_id?: number;
  chunk_size?: number;
  chunk_overlap?: number;
  parent_size?: number;
  parent_overlap?: number;
  llm_id?: number;
  is_active?: boolean;
}

export type KbUpdatePayload = Partial<KbCreatePayload>;

// ─── API calls ────────────────────────────────────────────────────────────────

/** GET /knowledge_bases  — paginated list */
export const getKnowledgeBaseList = (params: KbListQuery) =>
  http.request<KnowledgeBaseListResult>("get", baseUrlApi("knowledge_bases"), {
    params
  });

/** GET /knowledge_bases/options */
export const getKnowledgeBaseOptions = () =>
  http.request<{ data: KnowledgeBaseOption[] }>(
    "get",
    baseUrlApi("knowledge_bases/options")
  );

/** GET /knowledge_bases/:id */
export const getKnowledgeBase = (id: number) =>
  http.request<KnowledgeBaseItem>("get", baseUrlApi(`knowledge_bases/${id}`));

/** GET /knowledge_bases/:id/stats */
export const getKnowledgeBaseStats = (id: number) =>
  http.request<KnowledgeBaseStats>(
    "get",
    baseUrlApi(`knowledge_bases/${id}/stats`)
  );

/** POST /knowledge_bases */
export const createKnowledgeBase = (data: KbCreatePayload) =>
  http.request<KnowledgeBaseItem>("post", baseUrlApi("knowledge_bases"), {
    data
  });

/** PATCH /knowledge_bases/:id */
export const updateKnowledgeBase = (id: number, data: KbUpdatePayload) =>
  http.request<KnowledgeBaseItem>(
    "patch",
    baseUrlApi(`knowledge_bases/${id}`),
    { data }
  );

/** DELETE /knowledge_bases/:id */
export const deleteKnowledgeBase = (id: number) =>
  http.request("delete", baseUrlApi(`knowledge_bases/${id}`));

/** PATCH /knowledge_bases/:id/toggle */
export const toggleKnowledgeBase = (id: number) =>
  http.request("patch", baseUrlApi(`knowledge_bases/${id}/toggle`));
