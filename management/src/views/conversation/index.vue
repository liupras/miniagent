<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useSession } from "./utils/hook";
import { formatDateTime } from "./utils/format";
import MessageDialog from "./components/MessageDialog.vue";
import { hasAuth } from "@/router/utils";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";

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
    <el-form :inline="true" class="search-form">
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

    <div class="table-header">
      <span class="table-title">{{ t("chatSession.tableTitle") }}</span>
      <el-button
        :icon="Refresh"
        circle
        :title="t('buttons.refresh')"
        :disabled="!userId"
        :loading="loading"
        @click="onSearch"
      />
    </div>

    <el-table
      v-loading="loading"
      :data="dataList"
      :empty-text="emptyText"
      border
      row-key="session_id"
    >
      <el-table-column
        :label="t('chatSession.title')"
        prop="title"
        min-width="180"
        show-overflow-tooltip
      >
        <template #default="{ row }">{{ row.title || "-" }}</template>
      </el-table-column>
      <el-table-column
        :label="t('chatSession.sessionId')"
        prop="session_id"
        width="110"
        show-overflow-tooltip
      />
      <el-table-column
        :label="t('chatSession.agentId')"
        prop="agent_id"
        width="100"
      >
        <template #default="{ row }">{{ row.agent_id ?? "-" }}</template>
      </el-table-column>
      <el-table-column
        :label="t('chatSession.messageCount')"
        prop="message_count"
        width="110"
      />
      <el-table-column
        :label="t('form.createdAt')"
        prop="created_at"
        width="150"
        :formatter="(_row, _col, val) => formatDateTime(val)"
      />
      <el-table-column
        :label="t('form.updatedAt')"
        prop="updated_at"
        width="150"
        :formatter="(_row, _col, val) => formatDateTime(val)"
      />
      <el-table-column
        v-if="hasAuth('conversation:list') || hasAuth('conversation:delete')"
        :label="t('labels.operation')"
        width="180"
        fixed="right"
      >
        <template #default="{ row }">
          <el-button
            v-auth="'conversation:list'"
            type="primary"
            link
            @click="openMessages(row)"
          >
            {{ t("chatSession.viewMessages") }}
          </el-button>
          <el-button
            v-auth="'conversation:delete'"
            type="danger"
            link
            @click="handleDelete(row)"
          >
            {{ t("buttons.delete") }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="pagination.total"
        :page-sizes="[10, 20, 50, 100]"
        background
        layout="total, sizes, prev, pager, next, jumper"
        @size-change="handleSizeChange"
        @current-change="handleCurrentChange"
      />
    </div>

    <MessageDialog ref="messageDialogRef" />
  </div>
</template>

<style scoped>
.main {
  padding: 16px;
}

.search-form {
  margin-bottom: 12px;
}

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

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.table-title {
  font-size: 16px;
  font-weight: 600;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

@media (width <= 640px) {
  .user-select {
    width: 100%;
  }

  .search-form :deep(.el-form-item:first-child),
  .search-form :deep(.el-form-item:first-child .el-form-item__content) {
    width: 100%;
  }

  .pagination-bar {
    justify-content: flex-start;
    overflow-x: auto;
  }
}
</style>
