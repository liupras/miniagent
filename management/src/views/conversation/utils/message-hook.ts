import { ref, reactive } from "vue";
import { ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  getChatMessageList,
  deleteChatMessage,
  type ChatMessageResponse
} from "@/api/conversation";

export function useMessages() {
  const { t } = useI18n();

  const loading = ref(false);
  const messageList = ref<ChatMessageResponse[]>([]);
  const currentSessionId = ref<number>();
  const currentSessionTitle = ref<string>("");
  let requestVersion = 0;

  const pagination = reactive({
    total: 0,
    page: 1,
    pageSize: 20
  });

  async function fetchMessages() {
    if (!currentSessionId.value) return;
    const version = ++requestVersion;
    loading.value = true;
    try {
      const data = await getChatMessageList(currentSessionId.value, {
        page: pagination.page,
        page_size: pagination.pageSize
      });
      if (version === requestVersion) {
        messageList.value = data.items;
        pagination.total = data.total;
      }
    } finally {
      if (version === requestVersion) loading.value = false;
    }
  }

  /** Open the dialog for a given session. */
  function loadMessages(sessionId: number, title?: string) {
    currentSessionId.value = sessionId;
    currentSessionTitle.value = title ?? String(sessionId);
    pagination.page = 1;
    fetchMessages();
  }

  function handleSizeChange(val: number) {
    pagination.pageSize = val;
    fetchMessages();
  }

  function handleCurrentChange(val: number) {
    pagination.page = val;
    fetchMessages();
  }

  async function handleDeleteMessage(row: ChatMessageResponse) {
    await deleteChatMessage(row.id);
    ElMessage.success(t("messages.deleteSuccess"));
    if (messageList.value.length === 1 && pagination.page > 1) {
      pagination.page -= 1;
    }
    fetchMessages();
  }

  return {
    loading,
    messageList,
    currentSessionId,
    currentSessionTitle,
    pagination,
    loadMessages,
    handleSizeChange,
    handleCurrentChange,
    handleDeleteMessage
  };
}
