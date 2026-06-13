// src/api/tools.ts
import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export type ToolType = "function" | "api" | "smart_router" | "sql_agent";

export interface Tool {
  id: number;
  name: string;
  description: string | null;
  tool_type: ToolType;
  tool_schema: Record<string, unknown>;
  config: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ToolListResponse {
  total: number;
  page: number;
  page_size: number;
  data: Tool[];
}

export interface ToolListParams {
  page?: number;
  page_size?: number;
  tool_type?: ToolType | "";
  is_active?: boolean;
  keyword?: string;
}

export interface ToolStats {
  total: number;
  active: number;
  by_type: Record<string, number>;
}

export type ToolCreatePayload = Omit<Tool, "id" | "created_at" | "updated_at">;
export type ToolUpdatePayload = Partial<ToolCreatePayload>;

export const getToolList = (params?: ToolListParams) =>
  http.request<ToolListResponse>("get", baseUrlApi("admin/tools"), {
    params
  });

/** Get aggregate stats */
export const getToolStats = () =>
  http.request<ToolStats>("get", baseUrlApi("admin/tools/stats"));

/** Get a single tool */
export const getTool = (id: number) =>
  http.request<Tool>("get", baseUrlApi(`admin/tools/${id}`));

/** Create a tool */
export const createTool = (data: ToolCreatePayload) =>
  http.request<Tool>("post", baseUrlApi("admin/tools"), { data });

/** Partially update a tool */
export const updateTool = (id: number, data: ToolUpdatePayload) =>
  http.request<Tool>("patch", baseUrlApi(`admin/tools/${id}`), { data });

/** Toggle active status */
export const toggleTool = (id: number) =>
  http.request<Tool>("patch", baseUrlApi(`admin/tools/${id}/toggle`));

/** Delete a single tool */
export const deleteTool = (id: number) =>
  http.request<Tool>("delete", baseUrlApi(`admin/tools/${id}`));

/** Bulk delete */
export const bulkDeleteTools = (ids: number[]) =>
  http.request<{ deleted: number }>(
    "post",
    baseUrlApi("admin/tools/bulk-delete"),
    {
      data: ids
    }
  );
