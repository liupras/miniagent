import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export type LLMCapabilities = Record<string, unknown>;

export interface LLMItem {
  id: number;
  name: string;
  provider_name: string;
  base_url: string;
  api_key?: string | null;
  model_name: string;
  temperature: number;
  max_tokens: number;
  capabilities?: LLMCapabilities | null;
  created_at: string;
}

export interface LLMListParams {
  page?: number;
  page_size?: number;
  provider_name?: string;
  model_name?: string;
}

export interface LLMPageResult {
  total: number;
  page: number;
  page_size: number;
  data: LLMItem[];
}

export interface LLMCreatePayload {
  name: string;
  provider_name: string;
  base_url: string;
  api_key?: string | null;
  model_name: string;
  temperature: number;
  max_tokens: number;
  capabilities?: LLMCapabilities | null;
}

export type LLMUpdatePayload = Partial<LLMCreatePayload>;

const BASE_URL = "admin/llms";

export const getLLMList = (params: LLMListParams) =>
  http.request<LLMPageResult>("get", baseUrlApi(BASE_URL), { params });

export const getLLM = (id: number) =>
  http.request<LLMItem>("get", baseUrlApi(`${BASE_URL}/${id}`));

export const getLLMProviders = () =>
  http.request<string[]>("get", baseUrlApi(`${BASE_URL}/providers`));

export const createLLM = (data: LLMCreatePayload) =>
  http.request<LLMItem>("post", baseUrlApi(BASE_URL), { data });

export const updateLLM = (id: number, data: LLMUpdatePayload) =>
  http.request<LLMItem>("put", baseUrlApi(`${BASE_URL}/${id}`), { data });

export const deleteLLM = (id: number) =>
  http.request<void>("delete", baseUrlApi(`${BASE_URL}/${id}`));
