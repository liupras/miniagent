// src/views/document/utils/hook.tsx
import { reactive, ref, onBeforeUnmount, h } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, ElTag } from "element-plus";
import type { PaginationProps } from "@pureadmin/table";
import {
  getDocumentList,
  getDocumentDetail,
  addDocument,
  updateDocument,
  deleteDocument,
  subscribeTaskProgress,
  type DocumentRead,
  type DocumentStatus
} from "@/api/document";
import { getKnowledgeBaseOptions } from "@/api/knowledge_base";
import type {
  SearchFormState,
  UploadFormState,
  ProgressState,
  ProgressMode,
  KnowledgeBaseOption
} from "./types";

const STATUS_TAG_TYPE: Record<
  DocumentStatus,
  "info" | "warning" | "success" | "danger"
> = {
  pending: "info",
  processing: "warning",
  completed: "success",
  failed: "danger"
};

function formatFileSize(bytes?: number | null): string {
  if (!bytes && bytes !== 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

export function useDocument(initialKbId?: number | null) {
  const { t } = useI18n();

  // ── search / table state ─────────────────────────────────────────────
  const form = reactive<SearchFormState>({
    kb_id: initialKbId ?? null,
    status_filter: ""
  });

  const kbOptions = ref<KnowledgeBaseOption[]>([]);
  async function fetchKbOptions() {
    try {
      const res = await getKnowledgeBaseOptions();
      kbOptions.value = res;
    } catch {
      // dropdown is best-effort; list/CRUD calls will still surface their own errors
    }
  }

  const dataList = ref<DocumentRead[]>([]);
  const loading = ref(false);
  const pagination = reactive<PaginationProps>({
    total: 0,
    pageSize: 20,
    currentPage: 1,
    background: true
  });

  const columns: any[] = [
    { label: t("document.field.id"), prop: "id", width: 70 },
    {
      label: t("document.field.filename"),
      prop: "filename",
      minWidth: 200,
      showOverflowTooltip: true
    },
    {
      label: t("form.kbName.label"),
      prop: "kb_id",
      width: 160,
      formatter: (row: DocumentRead) =>
        kbOptions.value.find(kb => kb.id === row.kb_id)?.name ?? row.kb_id
    },
    { label: t("document.field.mimeType"), prop: "mime_type", width: 100 },
    {
      label: t("document.field.fileSize"),
      prop: "file_size",
      width: 110,
      formatter: (row: DocumentRead) => formatFileSize(row.file_size)
    },
    { label: t("document.field.chunkCount"), prop: "chunk_count", width: 90 },
    {
      label: t("document.field.status"),
      prop: "status",
      width: 120,
      cellRenderer: ({ row }: { row: DocumentRead }) =>
        h(
          ElTag,
          { type: STATUS_TAG_TYPE[row.status], effect: "light" },
          { default: () => t(`document.status.${row.status}`) }
        )
    },
    {
      label: t("labels.operation"),
      fixed: "right",
      width: 220,
      slot: "operation"
    }
  ];

  async function fetchList() {
    loading.value = true;
    try {
      const data = await getDocumentList({
        kb_id: form.kb_id ?? undefined,
        status_filter: form.status_filter || undefined,
        page: pagination.currentPage,
        page_size: pagination.pageSize
      });
      dataList.value = data.items;
      pagination.total = data.total;
    } finally {
      loading.value = false;
    }
  }

  function onSearch() {
    pagination.currentPage = 1;
    fetchList();
  }

  function resetForm() {
    form.kb_id = initialKbId ?? null;
    form.status_filter = "";
    onSearch();
  }

  function handleSizeChange(size: number) {
    pagination.pageSize = size;
    fetchList();
  }

  function handleCurrentChange(page: number) {
    pagination.currentPage = page;
    fetchList();
  }

  // ── detail dialog ────────────────────────────────────────────────────
  const detailVisible = ref(false);
  const detailRow = ref<DocumentRead | null>(null);

  async function openDetail(row: DocumentRead) {
    const data = await getDocumentDetail(row.kb_id, row.id);
    detailRow.value = data;
    detailVisible.value = true;
  }

  // ── upload / re-upload dialog ───────────────────────────────────────
  const uploadVisible = ref(false);
  const uploadForm = reactive<UploadFormState>({
    file: null,
    metadataText: ""
  });
  const uploadMode = ref<"add" | "update">("add");
  const activeDocId = ref<number | null>(null);
  const activeKbId = ref<number | null>(null);

  function openAddDialog() {
    uploadMode.value = "add";
    activeDocId.value = null;
    activeKbId.value = null;
    uploadForm.file = null;
    uploadForm.metadataText = "";
    uploadVisible.value = true;
  }

  function openUpdateDialog(row: DocumentRead) {
    uploadMode.value = "update";
    activeDocId.value = row.id;
    activeKbId.value = row.kb_id;
    uploadForm.file = null;
    uploadForm.metadataText = row.meta_data_json
      ? JSON.stringify(row.meta_data_json, null, 2)
      : "";
    uploadVisible.value = true;
  }

  function parseMetadata(): Record<string, any> | undefined {
    if (!uploadForm.metadataText.trim()) return undefined;
    try {
      return JSON.parse(uploadForm.metadataText);
    } catch {
      ElMessage.warning(t("document.message.metadataInvalid"));
      throw new Error("invalid metadata json");
    }
  }

  // ── SSE progress dialog ─────────────────────────────────────────────
  const progress = reactive<ProgressState>({
    visible: false,
    mode: "upload",
    taskId: "",
    stage: "",
    message: "",
    progress: 0,
    done: false,
    error: false
  });
  let activeSource: EventSource | null = null;

  function closeProgressSource() {
    activeSource?.close();
    activeSource = null;
  }

  function startProgress(
    taskId: string,
    mode: ProgressMode,
    onDone?: () => void
  ) {
    closeProgressSource();
    Object.assign(progress, {
      visible: true,
      mode,
      taskId,
      stage: "",
      message: t("document.message.taskStarted"),
      progress: 0,
      done: false,
      error: false
    });
    activeSource = subscribeTaskProgress(
      taskId,
      evt => {
        progress.stage = evt.stage;
        progress.message = evt.message;
        progress.progress = evt.progress;
        progress.done = evt.done;
        progress.error = evt.error;
        if (evt.done && !evt.error) {
          fetchList();
          onDone?.();
        }
      },
      () => {
        progress.error = true;
        progress.message = t("document.message.connectionLost");
      }
    );
  }

  function closeProgressDialog() {
    closeProgressSource();
    progress.visible = false;
  }

  // ── CRUD actions ─────────────────────────────────────────────────────
  async function submitUpload() {
    if (!uploadForm.file) {
      ElMessage.warning(t("document.message.fileRequired"));
      return;
    }
    let metadata: Record<string, any> | undefined;
    try {
      metadata = parseMetadata();
    } catch {
      return;
    }

    if (uploadMode.value === "add") {
      if (!form.kb_id) {
        ElMessage.warning(t("document.message.kbRequired"));
        return;
      }
      const data = await addDocument(form.kb_id, uploadForm.file, metadata);
      uploadVisible.value = false;
      startProgress(data.task_id, "upload");
    } else if (activeDocId.value != null && activeKbId.value != null) {
      const data = await updateDocument(
        activeKbId.value,
        activeDocId.value,
        uploadForm.file,
        metadata
      );
      uploadVisible.value = false;
      startProgress(data.task_id, "update");
    }
  }

  async function handleDelete(row: DocumentRead) {
    const data = await deleteDocument(row.kb_id, row.id);
    startProgress(data.task_id, "delete");
  }

  onBeforeUnmount(() => closeProgressSource());

  return {
    t,
    form,
    kbOptions,
    fetchKbOptions,
    columns,
    dataList,
    loading,
    pagination,
    onSearch,
    resetForm,
    handleSizeChange,
    handleCurrentChange,
    fetchList,
    detailVisible,
    detailRow,
    openDetail,
    uploadVisible,
    uploadForm,
    uploadMode,
    openAddDialog,
    openUpdateDialog,
    submitUpload,
    handleDelete,
    progress,
    closeProgressDialog
  };
}
