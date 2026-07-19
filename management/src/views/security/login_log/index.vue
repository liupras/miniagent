<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('loginLog.keyword')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          clearable
          class="w-64!"
          :placeholder="t('loginLog.keywordPlaceholder')"
          @keyup.enter="onSearch"
        />
      </el-form-item>
      <el-form-item :label="t('loginLog.eventType')" prop="eventType">
        <el-select
          v-model="searchForm.eventType"
          clearable
          class="w-40!"
          :placeholder="t('loginLog.allEvents')"
        >
          <el-option :label="t('loginLog.login')" value="LOGIN" />
          <el-option
            :label="t('loginLog.refreshToken')"
            value="REFRESH_TOKEN"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('loginLog.status')" prop="success">
        <el-select
          v-model="searchForm.success"
          clearable
          class="w-32!"
          :placeholder="t('loginLog.allStatuses')"
        >
          <el-option :label="t('loginLog.success')" value="true" />
          <el-option :label="t('loginLog.failure')" value="false" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('loginLog.timeRange')" prop="timeRange">
        <el-date-picker
          v-model="searchForm.timeRange"
          type="datetimerange"
          value-format="YYYY-MM-DDTHH:mm:ss"
          :start-placeholder="t('loginLog.startTime')"
          :end-placeholder="t('loginLog.endTime')"
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
      :title="t('loginLog.title')"
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
              <span>{{ row.username || t("loginLog.anonymous") }}</span>
              <span v-if="row.user_id" class="text-xs text-gray-400">
                ID: {{ row.user_id }}
              </span>
            </div>
          </template>
          <template #eventType="{ row }">
            <el-tag
              :type="row.event_type === 'LOGIN' ? 'primary' : 'warning'"
              effect="plain"
            >
              {{ eventLabel(row.event_type) }}
            </el-tag>
          </template>
          <template #status="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'">
              {{ row.success ? t("loginLog.success") : t("loginLog.failure") }}
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
      :title="t('loginLog.detailTitle')"
      width="760px"
      destroy-on-close
    >
      <div v-loading="detailLoading">
        <el-descriptions v-if="currentLog" :column="2" border>
          <el-descriptions-item label="ID">{{
            currentLog.id
          }}</el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.requestId')">
            <code>{{ currentLog.request_id }}</code>
          </el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.user')">
            {{ currentLog.username || t("loginLog.anonymous") }}
            <span v-if="currentLog.user_id"
              >(ID: {{ currentLog.user_id }})</span
            >
          </el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.ipAddress')">
            {{ currentLog.ip_address || "-" }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.eventType')">
            <el-tag
              :type="currentLog.event_type === 'LOGIN' ? 'primary' : 'warning'"
              effect="plain"
            >
              {{ eventLabel(currentLog.event_type) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.status')">
            <el-tag :type="currentLog.success ? 'success' : 'danger'">
              {{
                currentLog.success
                  ? t("loginLog.success")
                  : t("loginLog.failure")
              }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="t('form.createdAt')">
            {{ formatTime(currentLog.created_at) }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.failureReason')" :span="2">
            {{ currentLog.failure_reason || "-" }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('loginLog.userAgent')" :span="2">
            <span class="break-all">{{ currentLog.user_agent || "-" }}</span>
          </el-descriptions-item>
        </el-descriptions>
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
  getLoginLog,
  getLoginLogList,
  type LoginEventType,
  type LoginLogItem
} from "@/api/login_log";

defineOptions({ name: "LoginLogManagement" });

const { t } = useI18n();
const dateDefaultTime: [Date, Date] = [
  new Date(2000, 0, 1, 0, 0, 0),
  new Date(2000, 0, 1, 23, 59, 59)
];

const loading = ref(false);
const tableData = ref<LoginLogItem[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({
  keyword: "",
  eventType: "" as LoginEventType | "",
  success: "" as "true" | "false" | "",
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

const eventLabel = (eventType: LoginEventType) =>
  eventType === "LOGIN" ? t("loginLog.login") : t("loginLog.refreshToken");

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 75 },
  {
    label: t("loginLog.requestId"),
    prop: "request_id",
    minWidth: 170,
    slot: "requestId"
  },
  { label: t("loginLog.user"), prop: "username", minWidth: 135, slot: "user" },
  {
    label: t("loginLog.eventType"),
    prop: "event_type",
    width: 130,
    slot: "eventType"
  },
  { label: t("loginLog.status"), prop: "success", width: 100, slot: "status" },
  {
    label: t("loginLog.ipAddress"),
    prop: "ip_address",
    width: 135,
    formatter: ({ ip_address }) => ip_address || "-"
  },
  {
    label: t("loginLog.failureReason"),
    prop: "failure_reason",
    minWidth: 160,
    formatter: ({ failure_reason }) => failure_reason || "-"
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
    const result = await getLoginLogList({
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      keyword: searchForm.keyword.trim() || undefined,
      event_type: searchForm.eventType || undefined,
      success:
        searchForm.success === "" ? undefined : searchForm.success === "true",
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
    eventType: "",
    success: "",
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
const currentLog = ref<LoginLogItem>();

async function openDetail(row: LoginLogItem) {
  detailVisible.value = true;
  detailLoading.value = true;
  currentLog.value = undefined;
  try {
    currentLog.value = await getLoginLog(row.id);
  } finally {
    detailLoading.value = false;
  }
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

@media (width <= 760px) {
  :deep(.el-dialog) {
    width: 94% !important;
  }
}
</style>
