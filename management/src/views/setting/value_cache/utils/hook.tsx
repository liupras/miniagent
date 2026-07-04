import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  getCacheStoreStats,
  deleteCacheStoreKeys,
  clearCacheStoreNamespace,
  clearAllCacheStoreNamespaces,
  type CacheStoreStatsItem
} from "@/api/value_cache";

export function useCacheStore() {
  const { t } = useI18n();

  const loading = ref(false);
  const dataList = ref<CacheStoreStatsItem[]>([]);

  /** 主表格列定义，遵循项目 dynamicColumns 约定 */
  const columns: TableColumnList = [
    {
      label: t("valueCache.namespace"),
      prop: "namespace",
      minWidth: 160
    },
    {
      label: t("valueCache.backendType"),
      prop: "backend_type",
      width: 160
    },
    {
      label: t("valueCache.size"),
      prop: "size",
      width: 100
    },
    {
      label: t("labels.operation"),
      fixed: "right",
      width: 280,
      slot: "operation"
    }
  ];

  /** key 详情弹窗相关状态 */
  const keysDialogVisible = ref(false);
  const currentNamespace = ref<CacheStoreStatsItem | null>(null);

  async function onSearch() {
    loading.value = true;
    try {
      const data = await getCacheStoreStats();
      dataList.value = Object.values(data ?? {});
    } finally {
      loading.value = false;
    }
  }

  function openKeysDialog(row: CacheStoreStatsItem) {
    currentNamespace.value = row;
    keysDialogVisible.value = true;
  }

  async function refreshCurrentNamespace() {
    if (!currentNamespace.value) return;
    const data = await getCacheStoreStats(currentNamespace.value.namespace);
    currentNamespace.value =
      data?.[currentNamespace.value.namespace] ?? currentNamespace.value;
    // 同步刷新主表格中对应行
    const idx = dataList.value.findIndex(
      item => item.namespace === currentNamespace.value?.namespace
    );
    if (idx !== -1 && currentNamespace.value) {
      dataList.value[idx] = currentNamespace.value;
    }
  }

  /** 行内操作已经有 el-popconfirm 兜底确认，这里不再重复弹 ElMessageBox */
  async function handleClearNamespace(row: CacheStoreStatsItem) {
    const { cleared_count } = await clearCacheStoreNamespace(row.namespace);
    ElMessage.success(t("valueCache.clearSuccess", { count: cleared_count }));
    onSearch();
  }

  /** 工具栏按钮没有 popconfirm 锚点，用 ElMessageBox 做二次确认 */
  function handleClearAll() {
    ElMessageBox.confirm(t("valueCache.confirmClearAll"), t("labels.tip"), {
      confirmButtonText: t("buttons.confirm"),
      cancelButtonText: t("buttons.cancel"),
      type: "warning"
    }).then(async () => {
      const { results } = await clearAllCacheStoreNamespaces();
      const total = Object.values(results).reduce((a, b) => a + b, 0);
      ElMessage.success(t("valueCache.clearAllSuccess", { count: total }));
      onSearch();
    });
  }

  async function handleDeleteKeys(namespace: string, keys: string[]) {
    const { deleted_count } = await deleteCacheStoreKeys(namespace, keys);
    if (deleted_count > 0) {
      ElMessage.success(
        t("valueCache.deleteKeysSuccess", { count: deleted_count })
      );
    } else {
      ElMessage.warning(t("valueCache.keyNotFound"));
    }
    return deleted_count;
  }

  onMounted(() => {
    onSearch();
  });

  return {
    loading,
    dataList,
    columns,
    keysDialogVisible,
    currentNamespace,
    onSearch,
    openKeysDialog,
    refreshCurrentNamespace,
    handleClearNamespace,
    handleClearAll,
    handleDeleteKeys
  };
}
