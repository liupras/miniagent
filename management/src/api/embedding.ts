import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export interface EmbeddingItem {
  id: number;
  name: string;
  provider_name: string;
  base_url: string;
  api_key?: string | null;
  model_name: string;
  max_tokens: number;
}

export interface EmbeddingOption {
  id: number;
  name: string;
}

export interface EmbeddingListParams {
  name?: string;
  provider_name?: string;
  page?: number;
  page_size?: number;
}

export interface EmbeddingPageResult {
  total: number;
  page: number;
  page_size: number;
  items: EmbeddingItem[];
}

export interface EmbeddingPayload {
  name: string;
  provider_name: string;
  base_url: string;
  api_key?: string | null;
  model_name: string;
  max_tokens: number;
}

const BASE_URL = "admin/embeddings";

export const getEmbeddingList = (params: EmbeddingListParams) =>
  http.request<EmbeddingPageResult>("get", baseUrlApi(BASE_URL), { params });

export const getEmbeddingOptions = () =>
  http.request<EmbeddingOption[]>("get", baseUrlApi(`${BASE_URL}/options`));

export const createEmbedding = (data: EmbeddingPayload) =>
  http.request<EmbeddingItem>("post", baseUrlApi(BASE_URL), { data });

export const updateEmbedding = (id: number, data: EmbeddingPayload) =>
  http.request<EmbeddingItem>("patch", baseUrlApi(`${BASE_URL}/${id}`), {
    data
  });

export const deleteEmbedding = (id: number) =>
  http.request<number>("delete", baseUrlApi(`${BASE_URL}/${id}`));
