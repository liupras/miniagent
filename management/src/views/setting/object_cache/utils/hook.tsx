import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useI18n } from "vue-i18n";
import {
  getCacheStats,
  invalidateCacheKey,
  invalidateCacheAll,
  invalidateCacheEverywhere,
  type CacheStatsItem
} from "@/api/object_cache";

export function useCache() {
  const { t } = useI18n();

  const loading = ref(false);
  const dataList = ref<CacheStatsItem[]>([]);

  /** 主表格列定义，遵循项目 dynamicColumns 约定 */
  const columns: TableColumnList = [
    {
      label: t("cache.name"),
      prop: "name",
      minWidth: 180
    },
    {
      label: t("cache.size"),
      prop: "size",
      width: 100
    },
    {
      label: t("form.description.label"),
      prop: "description",
      minWidth: 220
    },
    {
      label: t("labels.operation"),
      fixed: "right",
      width: 260,
      slot: "operation"
    }
  ];

  /** key 失效弹窗相关状态 */
  const keysDialogVisible = ref(false);
  const currentCache = ref<CacheStatsItem | null>(null);

  async function onSearch() {
    loading.value = true;
    try {
      const data = await getCacheStats();
      dataList.value = Object.values(data ?? {});
    } finally {
      loading.value = false;
    }
  }

  function openKeysDialog(row: CacheStatsItem) {
    currentCache.value = row;
    keysDialogVisible.value = true;
  }

  async function refreshCurrentCache() {
    if (!currentCache.value) return;
    const data = await getCacheStats(currentCache.value.name);
    currentCache.value = data?.[currentCache.value.name] ?? currentCache.value;
    // 同步刷新主表格中对应行
    const idx = dataList.value.findIndex(
      item => item.name === currentCache.value?.name
    );
    if (idx !== -1 && currentCache.value) {
      dataList.value[idx] = currentCache.value;
    }
  }

  function handleInvalidateAll(row: CacheStatsItem) {
    ElMessageBox.confirm(
      t("cache.confirmInvalidateAll", { name: row.name }),
      t("cache.tip"),
      {
        confirmButtonText: t("buttons.confirm"),
        cancelButtonText: t("buttons.cancel"),
        type: "warning"
      }
    ).then(async () => {
      const { count } = await invalidateCacheAll(row.name);
      ElMessage.success(t("cache.invalidateAllSuccess", { count: count }));
      onSearch();
    });
  }

  async function handleInvalidateKey(name: string, key: any) {
    const { invalidated } = await invalidateCacheKey(name, key);
    if (invalidated) {
      ElMessage.success(t("cache.invalidateKeySuccess"));
    } else {
      ElMessage.warning(t("cache.keyNotFound"));
    }
    return invalidated;
  }

  async function handleInvalidateEverywhere(key: any) {
    const { results } = await invalidateCacheEverywhere(key);
    const hitCount = Object.values(results).filter(Boolean).length;
    ElMessage.success(
      t("cache.invalidateEverywhereResult", {
        hit: hitCount,
        total: Object.keys(results).length
      })
    );
    return results;
  }

  onMounted(() => {
    onSearch();
  });

  return {
    loading,
    dataList,
    columns,
    keysDialogVisible,
    currentCache,
    onSearch,
    openKeysDialog,
    refreshCurrentCache,
    handleInvalidateAll,
    handleInvalidateKey,
    handleInvalidateEverywhere
  };
}
