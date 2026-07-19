<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useSession } from "./utils/hook";
import { formatDateTime } from "./utils/format";
import MessageDialog from "./components/MessageDialog.vue";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasAuth } from "@/router/utils";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import View from "~icons/ep/view";
import Delete from "~icons/ep/delete";

defineOptions({ name: "ChatSessionManagement" });

const { t } = useI18n();

const {
  loading,
  userLoading,
  dataList,
  userOptions,
  userId,
  pagination,
  onSearch,
  search,
  resetSearch,
  handleSizeChange,
  handleCurrentChange,
  handleDelete
} = useSession();

const messageDialogRef = ref();
const emptyText = computed(() =>
  userId.value ? t("chatSession.noData") : t("chatSession.selectUserHint")
);
const tablePagination = computed(() => ({
  total: pagination.total,
  pageSize: pagination.pageSize,
  currentPage: pagination.page,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper",
  pageSizes: [10, 20, 50, 100]
}));

const columns: TableColumnList = [
  {
    label: t("chatSession.title"),
    prop: "title",
    minWidth: 220,
    slot: "title"
  },
  {
    label: t("chatSession.sessionId"),
    prop: "session_id",
    minWidth: 130,
    slot: "sessionId"
  },
  {
    label: t("chatSession.agentId"),
    prop: "agent_id",
    width: 110,
    formatter: ({ agent_id }) => agent_id ?? "-"
  },
  {
    label: t("chatSession.messageCount"),
    prop: "message_count",
    width: 120
  },
  {
    label: t("form.createdAt"),
    prop: "created_at",
    width: 165,
    formatter: ({ created_at }) => formatDateTime(created_at)
  },
  {
    label: t("form.updatedAt"),
    prop: "updated_at",
    width: 165,
    formatter: ({ updated_at }) => formatDateTime(updated_at)
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 190,
    fixed: "right",
    slot: "operation",
    hide: !hasAuth("conversation:list") && !hasAuth("conversation:delete")
  }
];

function formatUserLabel(user: (typeof userOptions.value)[number]) {
  const displayName = user.nickname?.trim() || user.username;
  const account = displayName === user.username ? "" : ` / ${user.username}`;
  return `${displayName}${account} (ID: ${user.id})`;
}

function openMessages(row: (typeof dataList.value)[number]) {
  messageDialogRef.value?.open(
    row.session_id,
    row.title || String(row.session_id)
  );
}
</script>

<template>
  <div class="main">
    <el-form
      :inline="true"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('chatSession.user')">
        <el-select
          v-model="userId"
          class="user-select"
          :loading="userLoading"
          :placeholder="t('chatSession.userPlaceholder')"
          filterable
          clearable
          @change="search"
        >
          <el-option
            v-for="user in userOptions"
            :key="user.id"
            :label="formatUserLabel(user)"
            :value="user.id"
          >
            <span>{{ user.nickname || user.username }}</span>
            <span class="user-option-meta">
              {{ user.username }} · ID {{ user.id }}
            </span>
          </el-option>
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button
          type="primary"
          :icon="Search"
          :loading="loading"
          :disabled="!userId"
          @click="search"
        >
          {{ t("buttons.search") }}
        </el-button>
        <el-button :icon="Refresh" @click="resetSearch">
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('chatSession.tableTitle')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #default="{ size, dynamicColumns }">
        <pure-table
          row-key="session_id"
          :data="dataList"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :empty-text="emptyText"
          :pagination="tablePagination"
          :paginationSmall="true"
          adaptive
          align-whole="center"
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <template #title="{ row }">
            <div class="session-title">
              <span class="font-medium">{{ row.title || "-" }}</span>
            </div>
          </template>
          <template #sessionId="{ row }">
            <code class="text-sm">{{ row.session_id }}</code>
          </template>
          <template #operation="{ row }">
            <el-button
              v-auth="'conversation:list'"
              type="primary"
              link
              :icon="View"
              @click="openMessages(row)"
            >
              {{ t("chatSession.viewMessages") }}
            </el-button>
            <el-button
              v-auth="'conversation:delete'"
              type="danger"
              link
              :icon="Delete"
              @click="handleDelete(row)"
            >
              {{ t("buttons.delete") }}
            </el-button>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <MessageDialog ref="messageDialogRef" />
  </div>
</template>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.user-select {
  width: 320px;
}

.user-option-meta {
  float: right;
  margin-left: 20px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.session-title {
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (width <= 640px) {
  .user-select {
    width: 100%;
  }

  .search-form :deep(.el-form-item:first-child),
  .search-form :deep(.el-form-item:first-child .el-form-item__content) {
    width: 100%;
  }
}
</style>
