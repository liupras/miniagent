import { ref, reactive, onMounted } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  getChatSessionList,
  deleteChatSession,
  type ChatSessionResponse
} from "@/api/conversation";

export function useSession(initialUserId?: number) {
  const { t } = useI18n();

  const loading = ref(false);
  const dataList = ref<ChatSessionResponse[]>([]);
  const userId = ref<number | undefined>(initialUserId);

  const pagination = reactive({
    total: 0,
    page: 1,
    pageSize: 20
  });

  async function onSearch() {
    if (!userId.value) {
      dataList.value = [];
      pagination.total = 0;
      return;
    }
    loading.value = true;
    try {
      const data = await getChatSessionList(userId.value, {
        page: pagination.page,
        page_size: pagination.pageSize
      });
      dataList.value = data.items;
      pagination.total = data.total;
    } finally {
      loading.value = false;
    }
  }

  function resetSearch() {
    pagination.page = 1;
    onSearch();
  }

  function handleSizeChange(val: number) {
    pagination.pageSize = val;
    onSearch();
  }

  function handleCurrentChange(val: number) {
    pagination.page = val;
    onSearch();
  }

  function handleDelete(row: ChatSessionResponse) {
    ElMessageBox.confirm(
      t("chatSession.deleteConfirm", { name: row.title || row.session_id }),
      t("buttons.warning"),
      { type: "warning" }
    )
      .then(async () => {
        await deleteChatSession(row.session_id);
        ElMessage.success(t("chatSession.deleteSuccess"));
        // if we deleted the last row on this page, step back a page
        if (dataList.value.length === 1 && pagination.page > 1) {
          pagination.page -= 1;
        }
        onSearch();
      })
      .catch(() => {});
  }

  onMounted(() => {
    if (userId.value) onSearch();
  });

  return {
    loading,
    dataList,
    userId,
    pagination,
    onSearch,
    resetSearch,
    handleSizeChange,
    handleCurrentChange,
    handleDelete
  };
}
