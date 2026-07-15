<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useSession } from "./utils/hook";
import { formatDateTime } from "./utils/format";
import MessageDialog from "./components/MessageDialog.vue";

defineOptions({ name: "ChatSessionManagement" });

const { t } = useI18n();

const {
  loading,
  dataList,
  userId,
  pagination,
  onSearch,
  resetSearch,
  handleSizeChange,
  handleCurrentChange,
  handleDelete
} = useSession();

const messageDialogRef = ref();

function openMessages(row: (typeof dataList.value)[number]) {
  messageDialogRef.value?.open(row.session_id, row.title || row.session_id);
}
</script>

<template>
  <div class="main">
    <el-form :inline="true" class="search-form">
      <el-form-item :label="t('chatSession.userId')">
        <el-input-number
          v-model="userId"
          :min="1"
          :controls="false"
          :placeholder="t('chatSession.userIdPlaceholder')"
          @keyup.enter="resetSearch"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="resetSearch">
          {{ t("buttons.search") }}
        </el-button>
      </el-form-item>
    </el-form>

    <el-table v-loading="loading" :data="dataList" border row-key="id">
      <el-table-column
        :label="t('chatSession.title')"
        prop="title"
        min-width="180"
        show-overflow-tooltip
      />
      <el-table-column
        :label="t('chatSession.sessionId')"
        prop="session_id"
        min-width="160"
        show-overflow-tooltip
      />
      <el-table-column
        :label="t('chatSession.agentId')"
        prop="agent_id"
        width="100"
      />
      <el-table-column
        :label="t('chatSession.messageCount')"
        prop="message_count"
        width="110"
      />
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
      <el-table-column :label="t('labels.operation')" width="200" fixed="right">
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
        layout="total, sizes, prev, pager, next"
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

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
