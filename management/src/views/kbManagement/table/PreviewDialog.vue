<script setup lang="ts">
defineOptions({
  name: "PreviewDialog"
});

import { ref, reactive, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  getTableColumns,
  getTableData,
  type ColumnInfo,
  type TableInfo
} from "@/api/table";

const props = defineProps<{
  modelValue: boolean;
  /** Table to preview. Loading starts once this becomes non-null while open. */
  table: TableInfo | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();

const { t } = useI18n();

const visible = computed({
  get: () => props.modelValue,
  set: value => emit("update:modelValue", value)
});

const loading = ref(false);
const columns = ref<ColumnInfo[]>([]);
const rows = ref<Record<string, any>[]>([]);
const total = ref(0);
const pagination = reactive({ page: 1, pageSize: 20 });

const dialogTitle = computed(() =>
  props.table ? `${props.table.schemaName}.${props.table.tableName}` : ""
);

// Reload from page 1 whenever the dialog opens for a (new) table.
watch(
  () => [props.modelValue, props.table] as const,
  async ([open, table]) => {
    // ✨ 1. 加上 async 关键字
    if (open && table) {
      // ✨ 2. 先执行「列结构加载」，并用 await 强行让代码在这里等待，直到它完全返回
      await loadColumns(table as TableInfo);

      // ✨ 3. 安全处理页码重置与「数据加载」
      if (pagination.page !== 1) {
        // 如果当前页码不是 1，这一步赋值会触发 el-pagination 的 @current-change 事件。
        // 该事件会自动调用 handlePageChange() -> loadData()。
        // 因为前面已经 await 确保列加载完成了，所以此时触发数据加载是绝对安全的，这里无需再手动调用。
        pagination.page = 1;
      } else {
        // 如果原本就是第 1 页，赋值为 1 不会触发组件的任何事件。
        // 此时我们需要手动使用 await 去安全地执行数据加载。
        await loadData(table as TableInfo);
      }
    }
  }
);

async function loadColumns(table: TableInfo) {
  columns.value = await getTableColumns(table.schemaName, table.tableName);
  //console.log(columns.value);
}

async function loadData(table: TableInfo) {
  loading.value = true;
  try {
    const res = await getTableData(table.schemaName, table.tableName, {
      page: pagination.page,
      pageSize: pagination.pageSize
    });
    //console.log(res);
    rows.value = res.rows;
    total.value = res.total;
  } finally {
    loading.value = false;
  }
}

function handlePageChange() {
  if (props.table) loadData(props.table);
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="80%"
    destroy-on-close
  >
    <el-table v-loading="loading" :data="rows" border height="480">
      <el-table-column
        v-for="col in columns"
        :key="col.name"
        :prop="col.name"
        :label="col.name"
        show-overflow-tooltip
      />
    </el-table>

    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.pageSize"
      style="margin-top: 12px; justify-content: flex-end"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="handlePageChange"
    />

    <template #footer>
      <el-button @click="visible = false">{{ t("buttons.close") }}</el-button>
    </template>
  </el-dialog>
</template>
