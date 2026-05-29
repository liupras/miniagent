import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

// ── Types ──────────────────────────────────────────────────────────────────

export interface LLMBrief {
  id: number;
  name: string;
}

export interface UserBrief {
  id: number;
  username: string;
}

export interface Agent {
  id: number;
  name: string;
  description?: string;
  system_prompt: string;
  llm_id?: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  llm?: LLMBrief;
  users: UserBrief[];
}

export interface AgentListParams {
  page?: number;
  page_size?: number;
  name?: string;
  llm_id?: number;
  user_id?: number;
  is_active?: boolean;
}

export interface AgentCreatePayload {
  name: string;
  description?: string | null;
  system_prompt: string;
  llm_id?: number | null;
  is_active?: boolean;
}

export type AgentUpdatePayload = Partial<AgentCreatePayload>;

export interface PageResult<T> {
  total: number;
  page: number;
  page_size: number;
  data: T[];
}

export interface ApiResponse<T = any> {
  code: number;
  message: string;
  data: T;
}

// ── Agent CRUD ─────────────────────────────────────────────────────────────

/** Paginated agent list with optional filters */
export const getAgentList = (params: AgentListParams) =>
  http.request<ApiResponse<PageResult<Agent>>>(
    "get",
    baseUrlApi("admin/agents"),
    {
      params
    }
  );

/** Single agent by id */
export const getAgentById = (id: number) =>
  http.request<ApiResponse<Agent>>("get", baseUrlApi(`admin/agents/${id}`));

/** Create a new agent */
export const createAgent = (data: AgentCreatePayload) =>
  http.request<ApiResponse<Agent>>("post", baseUrlApi("admin/agents"), {
    data
  });

/** Update an existing agent */
export const updateAgent = (id: number, data: AgentUpdatePayload) =>
  http.request<ApiResponse<Agent>>("put", baseUrlApi(`admin/agents/${id}`), {
    data
  });

/** Toggle is_active for an agent */
export const toggleAgentActive = (id: number) =>
  http.request<ApiResponse<null>>(
    "patch",
    baseUrlApi(`admin/agents/${id}/toggle`)
  );

/** Delete a single agent */
export const deleteAgent = (id: number) =>
  http.request<ApiResponse<null>>("delete", baseUrlApi(`admin/agents/${id}`));

/** Batch delete agents by id list */
export const batchDeleteAgents = (ids: number[]) =>
  http.request<ApiResponse<null>>("delete", baseUrlApi("admin/agents"), {
    data: ids
  });

// ── Option helpers (for dropdowns) ────────────────────────────────────────

/** Fetch all LLMs as id+name pairs for select dropdown */
export const getLLMOptions = () =>
  http.request<ApiResponse<LLMBrief[]>>(
    "get",
    baseUrlApi("admin/llms/options")
  );

/** Fetch all users as id+username pairs for select dropdown */
export const getUserOptions = () =>
  http.request<ApiResponse<UserBrief[]>>(
    "get",
    baseUrlApi("admin/users/options")
  );
