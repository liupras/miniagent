import type { DocumentRead, DocumentStatus } from "@/api/document";
import type { KnowledgeBaseOption } from "@/api/knowledge_base";

export interface SearchFormState {
  kb_id: number | null;
  status_filter: DocumentStatus | "";
}

export interface UploadFormState {
  file: File | null;
  /** Raw JSON text the user edits in the dialog; parsed before submit. */
  metadataText: string;
}

export type ProgressMode = "upload" | "update" | "delete";

export interface ProgressState {
  visible: boolean;
  mode: ProgressMode;
  taskId: string;
  stage: string;
  message: string;
  progress: number;
  done: boolean;
  error: boolean;
}

export type { DocumentRead, DocumentStatus, KnowledgeBaseOption };
