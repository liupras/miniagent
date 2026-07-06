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
} from "@/api/tables";

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
  ([open, table]) => {
    if (open && table) {
      pagination.page = 1;
      loadColumns(table as TableInfo);
      loadData(table as TableInfo);
    }
  }
);

async function loadColumns(table: TableInfo) {
  columns.value = await getTableColumns(table.schemaName, table.tableName);
}

async function loadData(table: TableInfo) {
  loading.value = true;
  try {
    const res = await getTableData(table.schemaName, table.tableName, {
      page: pagination.page,
      pageSize: pagination.pageSize
    });
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
