export interface AgentSummary {
  id: number;
  name: string;
  description?: string | null;
}

export interface ChatSession {
  session_id: number;
  title?: string | null;
  agent_id?: number | null;
  agent_name?: string | null;
  message_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ChatMessage {
  id: number | string;
  session_id?: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at?: string | null;
  streaming?: boolean;
}

export interface StreamEvent {
  event: "session" | "text" | "tool_start" | "error" | string;
  session_id?: number;
  chunk?: string;
  tools?: string[];
  message?: string;
}
