<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('auditLog.keyword')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          clearable
          class="w-64!"
          :placeholder="t('auditLog.keywordPlaceholder')"
          @keyup.enter="onSearch"
        />
      </el-form-item>
      <el-form-item :label="t('auditLog.action')" prop="action">
        <el-select
          v-model="searchForm.action"
          clearable
          class="w-36!"
          :placeholder="t('auditLog.allActions')"
        >
          <el-option
            v-for="action in actionOptions"
            :key="action"
            :label="action"
            :value="action"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('auditLog.status')" prop="status">
        <el-select
          v-model="searchForm.status"
          clearable
          class="w-32!"
          :placeholder="t('auditLog.allStatuses')"
        >
          <el-option :label="t('auditLog.success')" value="success" />
          <el-option :label="t('auditLog.failure')" value="failure" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('auditLog.timeRange')" prop="timeRange">
        <el-date-picker
          v-model="searchForm.timeRange"
          type="datetimerange"
          value-format="YYYY-MM-DDTHH:mm:ss"
          :start-placeholder="t('auditLog.startTime')"
          :end-placeholder="t('auditLog.endTime')"
          :default-time="dateDefaultTime"
          class="w-88!"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :icon="Search" @click="onSearch">
          {{ t("buttons.search") }}
        </el-button>
        <el-button :icon="Refresh" @click="onReset">
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('auditLog.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #default="{ size, dynamicColumns }">
        <pure-table
          row-key="id"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :pagination="pagination"
          :paginationSmall="true"
          adaptive
          align-whole="center"
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <template #requestId="{ row }">
            <el-tooltip :content="row.request_id" placement="top">
              <code class="request-id">{{ row.request_id }}</code>
            </el-tooltip>
          </template>
          <template #user="{ row }">
            <div class="flex flex-col items-start">
              <span>{{ row.username || t("auditLog.anonymous") }}</span>
              <span v-if="row.user_id" class="text-xs text-gray-400">
                ID: {{ row.user_id }}
              </span>
            </div>
          </template>
          <template #target="{ row }">
            <div class="flex flex-col items-start">
              <el-tag size="small" effect="plain">
                {{ row.target_type }}
              </el-tag>
              <code class="mt-1 max-w-full truncate text-xs">
                {{ row.target_id }}
              </code>
            </div>
          </template>
          <template #action="{ row }">
            <el-tag :type="actionTagType(row.action)" effect="plain">
              {{ row.action }}
            </el-tag>
          </template>
          <template #status="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'">
              {{
                row.status === "success"
                  ? t("auditLog.success")
                  : t("auditLog.failure")
              }}
            </el-tag>
          </template>
          <template #operation="{ row }">
            <el-button
              type="primary"
              link
              :icon="View"
              @click="openDetail(row)"
            >
              {{ t("buttons.view") }}
            </el-button>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <el-dialog
      v-model="detailVisible"
      :title="t('auditLog.detailTitle')"
      width="900px"
      destroy-on-close
    >
      <div v-loading="detailLoading">
        <el-descriptions v-if="currentLog" :column="2" border>
          <el-descriptions-item label="ID">
            {{ currentLog.id }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.requestId')">
            <code>{{ currentLog.request_id }}</code>
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.user')">
            {{ currentLog.username || t("auditLog.anonymous") }}
            <span v-if="currentLog.user_id">
              (ID: {{ currentLog.user_id }})
            </span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.ipAddress')">
            {{ currentLog.ip_address || "-" }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.targetType')">
            {{ currentLog.target_type }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.targetId')">
            <code>{{ currentLog.target_id }}</code>
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.action')">
            <el-tag :type="actionTagType(currentLog.action)" effect="plain">
              {{ currentLog.action }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.status')">
            <el-tag
              :type="currentLog.status === 'success' ? 'success' : 'danger'"
            >
              {{
                currentLog.status === "success"
                  ? t("auditLog.success")
                  : t("auditLog.failure")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('form.createdAt')">
            {{ formatTime(currentLog.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('auditLog.description')" :span="2">
            {{ currentLog.description || "-" }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="currentLog" class="snapshot-grid mt-4">
          <section class="snapshot-card">
            <h3>{{ t("auditLog.beforeValue") }}</h3>
            <pre v-if="currentLog.before_value != null">{{
              formatSnapshot(currentLog.before_value)
            }}</pre>
            <el-empty v-else :description="t('auditLog.noSnapshot')" />
          </section>
          <section class="snapshot-card">
            <h3>{{ t("auditLog.afterValue") }}</h3>
            <pre v-if="currentLog.after_value != null">{{
              formatSnapshot(currentLog.after_value)
            }}</pre>
            <el-empty v-else :description="t('auditLog.noSnapshot')" />
          </section>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">
          {{ t("buttons.close") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { FormInstance } from "element-plus";
import dayjs from "dayjs";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import View from "~icons/ep/view";
import { PureTableBar } from "@/components/RePureTableBar";
import {
  getAuditLog,
  getAuditLogList,
  type AuditAction,
  type AuditLogItem,
  type AuditStatus
} from "@/api/audit_log";

defineOptions({ name: "AuditLogManagement" });

const { t } = useI18n();
const actionOptions: AuditAction[] = ["CREATE", "UPDATE", "DELETE", "EXECUTE"];
const dateDefaultTime: [Date, Date] = [
  new Date(2000, 0, 1, 0, 0, 0),
  new Date(2000, 0, 1, 23, 59, 59)
];

const loading = ref(false);
const tableData = ref<AuditLogItem[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({
  keyword: "",
  action: "" as AuditAction | "",
  status: "" as AuditStatus | "",
  timeRange: [] as string[]
});
const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper",
  pageSizes: [10, 20, 50, 100]
});

const formatTime = (value?: string | null) =>
  value ? dayjs(value).format("YYYY-MM-DD HH:mm:ss") : "-";

function actionTagType(action: AuditAction) {
  const types = {
    CREATE: "success",
    UPDATE: "warning",
    DELETE: "danger",
    EXECUTE: "primary"
  } as const;
  return types[action] || "info";
}

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 75 },
  {
    label: t("auditLog.requestId"),
    prop: "request_id",
    minWidth: 170,
    slot: "requestId"
  },
  {
    label: t("auditLog.user"),
    prop: "username",
    minWidth: 135,
    slot: "user"
  },
  {
    label: t("auditLog.target"),
    prop: "target_type",
    minWidth: 180,
    slot: "target"
  },
  {
    label: t("auditLog.action"),
    prop: "action",
    width: 105,
    slot: "action"
  },
  {
    label: t("auditLog.status"),
    prop: "status",
    width: 100,
    slot: "status"
  },
  {
    label: t("auditLog.ipAddress"),
    prop: "ip_address",
    width: 135,
    formatter: ({ ip_address }) => ip_address || "-"
  },
  {
    label: t("form.createdAt"),
    prop: "created_at",
    width: 175,
    formatter: ({ created_at }) => formatTime(created_at)
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 90,
    fixed: "right",
    slot: "operation"
  }
];

async function fetchData() {
  loading.value = true;
  try {
    const result = await getAuditLogList({
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      keyword: searchForm.keyword.trim() || undefined,
      action: searchForm.action || undefined,
      status: searchForm.status || undefined,
      created_from: searchForm.timeRange[0] || undefined,
      created_to: searchForm.timeRange[1] || undefined
    });
    tableData.value = result.data;
    pagination.total = result.total;
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pagination.currentPage = 1;
  fetchData();
}

function onReset() {
  searchFormRef.value?.resetFields();
  Object.assign(searchForm, {
    keyword: "",
    action: "",
    status: "",
    timeRange: []
  });
  onSearch();
}

function handleSizeChange(size: number) {
  pagination.pageSize = size;
  fetchData();
}

function handleCurrentChange(page: number) {
  pagination.currentPage = page;
  fetchData();
}

const detailVisible = ref(false);
const detailLoading = ref(false);
const currentLog = ref<AuditLogItem>();

async function openDetail(row: AuditLogItem) {
  detailVisible.value = true;
  detailLoading.value = true;
  currentLog.value = undefined;
  try {
    currentLog.value = await getAuditLog(row.id);
  } finally {
    detailLoading.value = false;
  }
}

function formatSnapshot(value: unknown) {
  return JSON.stringify(value, null, 2);
}

fetchData();
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.request-id {
  display: inline-block;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
  white-space: nowrap;
}

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.snapshot-card {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
}

.snapshot-card h3 {
  padding: 10px 14px;
  margin: 0;
  font-size: 14px;
  background: var(--el-fill-color-light);
  border-bottom: 1px solid var(--el-border-color);
}

.snapshot-card pre {
  min-height: 180px;
  max-height: 420px;
  padding: 14px;
  margin: 0;
  overflow: auto;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (width <= 760px) {
  :deep(.el-dialog) {
    width: 94% !important;
  }

  .snapshot-grid {
    grid-template-columns: 1fr;
  }
}
</style>
