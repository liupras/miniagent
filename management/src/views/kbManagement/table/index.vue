<script setup lang="ts">
defineOptions({
  name: "TableManagement"
});

import { ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import { PureTableBar } from "@/components/RePureTableBar";
import type { TableColumns } from "@pureadmin/table";
import ImportDialog from "./ImportDialog.vue";
import PreviewDialog from "./PreviewDialog.vue";
import {
  getSchemas,
  getTables,
  deleteTable,
  type SchemaInfo,
  type TableInfo
} from "@/api/tables";

const { t } = useI18n();

const schemas = ref<SchemaInfo[]>([]);
const currentSchema = ref("main");
const tableList = ref<TableInfo[]>([]);
const loading = ref(false);

const columns: TableColumns[] = [
  { label: t("tableManagement.tableName"), prop: "tableName" },
  { label: t("tableManagement.rowCount"), prop: "rowCount", width: 120 },
  { label: t("tableManagement.columnCount"), prop: "columnCount", width: 120 },
  {
    label: t("tableManagement.operations"),
    fixed: "right",
    width: 220,
    slot: "operation"
  }
];

async function loadSchemas() {
  schemas.value = await getSchemas();
  if (
    schemas.value.length &&
    !schemas.value.some(s => s.schemaName === currentSchema.value)
  ) {
    currentSchema.value = schemas.value[0].schemaName;
  }
}

async function loadTables() {
  loading.value = true;
  try {
    tableList.value = await getTables(currentSchema.value);
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  await loadSchemas();
  await loadTables();
}

onMounted(refresh);

/* ───────────────────────────── Delete table ───────────────────────────── */

async function handleDelete(row: TableInfo) {
  await deleteTable(row.schemaName, row.tableName);
  ElMessage.success(t("tableManagement.deleteSuccess"));
  await loadTables();
}

/* ───────────────────────────── Import dialog ───────────────────────────── */

const importVisible = ref(false);

function openImportDialog() {
  importVisible.value = true;
}

async function handleImportSuccess(result: { schemaName: string }) {
  currentSchema.value = result.schemaName;
  await refresh();
}

/* ───────────────────────────── Preview dialog ───────────────────────────── */

const previewVisible = ref(false);
const previewTarget = ref<TableInfo | null>(null);

function openPreview(row: TableInfo) {
  previewTarget.value = row;
  previewVisible.value = true;
}
</script>

<template>
  <div class="main">
    <PureTableBar
      :title="t('tableManagement.title')"
      :columns="columns"
      @refresh="refresh"
    >
      <template #buttons>
        <el-select
          v-model="currentSchema"
          style="width: 180px; margin-right: 12px"
          @change="loadTables"
        >
          <el-option
            v-for="s in schemas"
            :key="s.schemaName"
            :label="s.schemaName"
            :value="s.schemaName"
          />
        </el-select>
        <el-button
          v-auth="'table:add'"
          type="primary"
          @click="openImportDialog"
        >
          {{ t("tableManagement.importTable") }}
        </el-button>
      </template>

      <template v-slot="{ size, dynamicColumns }">
        <pure-table
          row-key="tableName"
          :data="tableList"
          :columns="dynamicColumns"
          :loading="loading"
          :size="size"
        >
          <template #operation="{ row }">
            <el-button
              v-auth="'table:list'"
              link
              type="primary"
              @click="openPreview(row)"
            >
              {{ t("tableManagement.preview") }}
            </el-button>
            <el-popconfirm
              :title="
                t('tableManagement.deleteConfirm', { tableName: row.tableName })
              "
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button v-auth="'table:delete'" link type="danger">
                  {{ t("tableManagement.delete") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <ImportDialog
      v-model="importVisible"
      :schema-name="currentSchema"
      @success="handleImportSuccess"
    />

    <PreviewDialog v-model="previewVisible" :table="previewTarget" />
  </div>
</template>
