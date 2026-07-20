import { API_BASE_URL, http, refreshAccessToken } from "./http";
import { getSession } from "../utils/session";
import type {
  AgentSummary,
  ChatMessage,
  ChatSession,
  StreamEvent,
} from "../types/chat";

interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

interface AgentListData {
  version: string;
  items: AgentSummary[];
}

interface PageData<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

export async function getAvailableAgents() {
  const response = await http.get<ApiResponse<AgentListData>>(
    "/api/v1/agent/available",
  );
  return response.data.data;
}

export async function getSessions(query = "") {
  const response = await http.get<ApiResponse<PageData<ChatSession>>>(
    "/api/v1/agent/sessions",
    { params: { query: query || undefined, page_size: 100 } },
  );
  return response.data.data;
}

export async function getMessages(sessionId: number) {
  const response = await http.get<ApiResponse<PageData<ChatMessage>>>(
    `/api/v1/agent/sessions/${sessionId}/messages`,
    { params: { page_size: 500 } },
  );
  return response.data.data;
}

export async function renameSession(sessionId: number, title: string) {
  await http.patch(`/api/v1/agent/sessions/${sessionId}`, { title });
}

export async function deleteSession(sessionId: number) {
  await http.delete(`/api/v1/agent/sessions/${sessionId}`);
}

async function streamRequest(
  body: Record<string, unknown>,
  signal?: AbortSignal,
  retried = false,
): Promise<Response> {
  const token = getSession()?.accessToken;
  const response = await fetch(`${API_BASE_URL}/api/v1/agent/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });

  if (response.status === 401 && !retried) {
    await refreshAccessToken();
    return streamRequest(body, signal, true);
  }
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const error = await response.json();
      message = error.detail || error.message || message;
    } catch {
      // Keep the HTTP status when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response;
}

function parseEventFrame(frame: string): StreamEvent | null {
  const data = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) return null;
  try {
    return JSON.parse(data) as StreamEvent;
  } catch {
    return { event: "text", chunk: data };
  }
}

export async function streamAgentMessage(options: {
  agentId: number;
  query: string;
  sessionId?: number | null;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}) {
  const response = await streamRequest(
    {
      agent_id: options.agentId,
      query: options.query,
      session_id: options.sessionId || null,
    },
    options.signal,
  );
  if (!response.body) throw new Error("Streaming is not supported");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const event = parseEventFrame(frame);
      if (event) options.onEvent(event);
    }
    if (done) break;
  }

  const finalEvent = parseEventFrame(buffer);
  if (finalEvent) options.onEvent(finalEvent);
}
