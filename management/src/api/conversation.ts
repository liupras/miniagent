import { http } from "@/utils/http";
import { baseUrlApi } from "./utils";

export interface ChatSessionResponse {
  session_id: number;
  title: string | null;
  user_id: number;
  agent_id: number | null;
  message_count: number;
  total_tokens: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface ChatSessionListOut {
  total: number;
  page: number;
  page_size: number;
  items: ChatSessionResponse[];
}

export type ChatMessageRole = "user" | "assistant" | "system";

export interface ChatMessageResponse {
  id: number;
  session_id: number;
  role: ChatMessageRole;
  content: string;
  created_at: string | null;
}

export interface ChatMessageListOut {
  total: number;
  page: number;
  page_size: number;
  items: ChatMessageResponse[];
}

export interface PageParams {
  page: number;
  page_size: number;
}

const BASE_URL = "admin/conversation";

/** Get a single chat session by its business session_id. */
export const getChatSession = (sessionId: string) => {
  return http.request<ChatSessionResponse>(
    "get",
    baseUrlApi(`${BASE_URL}/sessions/${sessionId}`)
  );
};

/** List chat sessions for a user, paginated. */
export const getChatSessionList = (userId: number, params: PageParams) => {
  return http.request<ChatSessionListOut>(
    "get",
    baseUrlApi(`${BASE_URL}/users/${userId}/sessions`),
    { params }
  );
};

/** Delete a chat session and all its messages (cascade). */
export const deleteChatSession = (sessionId: string) => {
  return http.request<null>(
    "delete",
    baseUrlApi(`${BASE_URL}/sessions/${sessionId}`)
  );
};

/** Delete a single chat message. */
export const deleteChatMessage = (messageId: number) => {
  return http.request<null>(
    "delete",
    baseUrlApi(`${BASE_URL}/messages/${messageId}`)
  );
};

/** Get chat messages for a session, paginated. */
export const getChatMessageList = (sessionId: string, params: PageParams) => {
  return http.request<ChatMessageListOut>(
    "get",
    baseUrlApi(`${BASE_URL}/sessions/${sessionId}/messages`),
    { params }
  );
};
