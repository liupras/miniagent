<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMessages } from "../utils/message-hook";
import { formatDateTime } from "../utils/format";
import { hasAuth } from "@/router/utils";
import Delete from "~icons/ep/delete";

const { t } = useI18n();

const visible = ref(false);

const {
  loading,
  messageList,
  currentSessionTitle,
  pagination,
  loadMessages,
  handleSizeChange,
  handleCurrentChange,
  handleDeleteMessage
} = useMessages();

/** Called by the parent (session list) to open this dialog. */
function open(sessionId: number, title?: string) {
  visible.value = true;
  loadMessages(sessionId, title);
}

type TagType = "primary" | "success" | "info" | "warning" | "danger";

const roleTagType: Record<string, TagType> = {
  user: "primary",
  assistant: "success",
  system: "info"
};

defineExpose({ open });
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('chatMessage.dialogTitle', { name: currentSessionTitle })"
    width="90%"
    top="5vh"
    class="message-dialog"
    destroy-on-close
  >
    <el-table
      v-loading="loading"
      :data="messageList"
      :empty-text="t('chatMessage.noData')"
      row-key="id"
      max-height="65vh"
      border
    >
      <el-table-column :label="t('chatMessage.role')" prop="role" width="110">
        <template #default="{ row }">
          <el-tag :type="roleTagType[row.role] || 'info'" size="small">
            {{
              roleTagType[row.role]
                ? t(`chatMessage.roles.${row.role}`)
                : row.role
            }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column :label="t('chatMessage.content')" prop="content">
        <template #default="{ row }">
          <div class="message-content">{{ row.content }}</div>
        </template>
      </el-table-column>

      <el-table-column
        :label="t('form.createdAt')"
        prop="created_at"
        width="150"
        :formatter="(_row, _col, val) => formatDateTime(val)"
      />

      <el-table-column
        v-if="hasAuth('conversation:delete')"
        :label="t('labels.operation')"
        width="90"
        fixed="right"
      >
        <template #default="{ row }">
          <el-popconfirm
            :title="t('chatMessage.deleteConfirm', { id: row.id })"
            @confirm="handleDeleteMessage(row)"
          >
            <template #reference>
              <el-button
                v-auth="'conversation:delete'"
                type="danger"
                link
                :icon="Delete"
              >
                {{ t("buttons.delete") }}
              </el-button>
            </template>
          </el-popconfirm>
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

    <template #footer>
      <el-button @click="visible = false">{{ t("buttons.close") }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.message-content {
  max-height: 160px;
  padding-right: 4px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}

:global(.message-dialog) {
  max-width: 1100px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
