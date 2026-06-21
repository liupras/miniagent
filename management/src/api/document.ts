import { http } from "@/utils/http";
import { baseUrlApi } from "@/api/utils";

/** Mirrors backend DocumentRead.status */
export type DocumentStatus = "pending" | "processing" | "completed" | "failed";

export interface DocumentRead {
  id: number;
  kb_id: number;
  hash_value: string;
  filename: string;
  mime_type: string;
  file_size?: number | null;
  file_uri?: string | null;
  storage_type: string;
  page_count: number;
  chunk_count: number;
  meta_data_json?: Record<string, any> | null;
  status: DocumentStatus;
  error_message?: string | null;
}

export interface DocumentListOut {
  total: number;
  page: number;
  page_size: number;
  items: DocumentRead[];
}

/** Returned by add/update/delete — heavy operations run in the background,
 *  progress is streamed back over SSE keyed by task_id. */
export interface TaskCreatedResponse {
  task_id: string;
  message: string;
}

export interface DocumentListParams {
  kbId?: number;
  status_filter?: DocumentStatus | "";
  page?: number;
  page_size?: number;
}

/** GET /{kb_id}/documents — http interceptor already unwraps to ApiResponse.data */
export const getDocumentList = (params?: DocumentListParams) =>
  http.request<DocumentListOut>("get", baseUrlApi(`admin/documents`), {
    params
  });

/** GET /{kb_id}/documents/{doc_id} */
export const getDocumentDetail = (kbId: number, docId: number) =>
  http.request<DocumentRead>(
    "get",
    baseUrlApi(`admin/documents/${kbId}/${docId}`)
  );

/** POST /{kb_id}/documents — multipart upload, kicks off a background task */
export const addDocument = (
  kbId: number,
  file: File,
  metadata?: Record<string, any>
) => {
  const form = new FormData();
  form.append("file", file);
  if (metadata) form.append("metadata", JSON.stringify(metadata));
  return http.request<TaskCreatedResponse>(
    "post",
    baseUrlApi(`admin/documents/${kbId}`),
    {
      data: form,
      headers: { "Content-Type": "multipart/form-data" }
    }
  );
};

/** PUT /{kb_id}/documents/{doc_id} — replace file content, kicks off a background task */
export const updateDocument = (
  kbId: number,
  docId: number,
  file: File,
  metadata?: Record<string, any>
) => {
  const form = new FormData();
  form.append("file", file);
  if (metadata) form.append("metadata", JSON.stringify(metadata));
  return http.request<TaskCreatedResponse>(
    "put",
    baseUrlApi(`admin/documents/${kbId}/${docId}`),
    { data: form, headers: { "Content-Type": "multipart/form-data" } }
  );
};

/** DELETE /{kb_id}/documents/{doc_id} — kicks off a background task */
export const deleteDocument = (kbId: number, docId: number) => {
  return http.request<TaskCreatedResponse>(
    "delete",
    baseUrlApi(`admin/documents/${kbId}/${docId}`)
  );
};

/** Mirrors the SSE payload emitted by ProgressTracker (see task.py docstring) */
export interface ProgressEvent {
  stage: string;
  message: string;
  progress: number;
  done: boolean;
  error: boolean;
  ts: string;
}

/**
 * Open an SSE connection to /{task_id}/progress and stream events back via
 * `onMessage`. The connection auto-closes once `done` or `error` arrives, or
 * on transport error. Caller may also close the returned EventSource early
 * (e.g. if the user closes the progress dialog).
 */
export const subscribeTaskProgress = (
  taskId: string,
  onMessage: (evt: ProgressEvent) => void,
  onError?: (err: Event) => void
): EventSource => {
  const es = new EventSource(baseUrlApi(`admin/tasks/${taskId}/progress`));
  es.onmessage = e => {
    try {
      const data: ProgressEvent = JSON.parse(e.data);
      onMessage(data);
      if (data.done || data.error) es.close();
    } catch {
      // keepalive comment lines (": keepalive") never reach onmessage; ignore
      // anything else that fails to parse rather than crashing the stream.
    }
  };
  es.onerror = e => {
    onError?.(e);
    es.close();
  };
  return es;
};
