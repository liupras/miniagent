import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export interface PromptItem {
  id: number;
  key: string;
  lang: string;
  value: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PromptListParams {
  page?: number;
  page_size?: number;
  keyword?: string;
  lang?: string;
}

export interface PromptPageResult {
  total: number;
  page: number;
  page_size: number;
  data: PromptItem[];
}

export interface PromptCreatePayload {
  key: string;
  lang: string;
  value: string;
  description?: string | null;
}

export interface PromptUpdatePayload {
  value: string;
  description?: string | null;
}

const BASE_URL = "admin/prompts";

export const getPromptList = (params: PromptListParams) =>
  http.request<PromptPageResult>("get", baseUrlApi(BASE_URL), { params });

export const getPromptLanguages = () =>
  http.request<string[]>("get", baseUrlApi(`${BASE_URL}/languages`));

export const createPrompt = (data: PromptCreatePayload) =>
  http.request<PromptItem>("post", baseUrlApi(BASE_URL), { data });

export const updatePrompt = (
  key: string,
  lang: string,
  data: PromptUpdatePayload
) =>
  http.request<PromptItem>("put", baseUrlApi(`${BASE_URL}/detail`), {
    params: { key, lang },
    data
  });

export const deletePrompt = (key: string, lang: string) =>
  http.request<void>("delete", baseUrlApi(`${BASE_URL}/detail`), {
    params: { key, lang }
  });
