import { ref, reactive } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
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
  const currentSessionId = ref<string>("");
  const currentSessionTitle = ref<string>("");

  const pagination = reactive({
    total: 0,
    page: 1,
    pageSize: 20
  });

  async function fetchMessages() {
    if (!currentSessionId.value) return;
    loading.value = true;
    try {
      const data = await getChatMessageList(currentSessionId.value, {
        page: pagination.page,
        page_size: pagination.pageSize
      });
      messageList.value = data.items;
      pagination.total = data.total;
    } finally {
      loading.value = false;
    }
  }

  /** Open the dialog for a given session. */
  function loadMessages(sessionId: string, title?: string) {
    currentSessionId.value = sessionId;
    currentSessionTitle.value = title ?? sessionId;
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

  function handleDeleteMessage(row: ChatMessageResponse) {
    ElMessageBox.confirm(
      t("messages.deleteConfirm", { name: row.session_id }),
      t("buttons.warning"),
      {
        type: "warning"
      }
    )
      .then(async () => {
        await deleteChatMessage(row.id);
        ElMessage.success(t("messages.deleteSuccess"));
        if (messageList.value.length === 1 && pagination.page > 1) {
          pagination.page -= 1;
        }
        fetchMessages();
      })
      .catch(() => {});
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
