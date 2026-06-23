<script setup lang="ts">
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import type { UploadFile } from "element-plus";
import { PureTableBar } from "@/components/RePureTableBar";
import ProgressDialog from "./utils/ProgressDialog.vue";
import { useDocument } from "./utils/hook";
import ChunkViewDialog from "./utils/ChunkViewDialog.vue";

defineOptions({ name: "KbDocument" });

const { t } = useI18n();
const route = useRoute();
// If this page is still nested under a KnowledgeBase detail route
// (e.g. /kb/:id/documents) we use that as the default; the new
// "Knowledge Base" search field lets the user switch it from here too.
const initialKbId = route.params.id ? Number(route.params.id) : null;

const {
  form,
  kbOptions,
  fetchKbOptions,
  columns,
  dataList,
  loading,
  pagination,
  onSearch,
  resetForm,
  handleSizeChange,
  handleCurrentChange,
  fetchList,
  detailVisible,
  detailRow,
  openDetail,
  uploadVisible,
  uploadForm,
  uploadMode,
  openAddDialog,
  openUpdateDialog,
  submitUpload,
  handleDelete,
  progress,
  closeProgressDialog,
  chunkVisible,
  chunkDoc,
  openChunkView
} = useDocument(initialKbId);

fetchKbOptions();
fetchList();

function onFileChange(uploadFile: UploadFile) {
  if (uploadFile.raw) {
    uploadForm.file = uploadFile.raw;
  }
}
</script>

<template>
  <div class="main">
    <el-form :inline="true" :model="form" class="search-form bg-bg_color">
      <el-form-item :label="t('document.search.kbLabel')">
        <el-select
          v-model="form.kb_id"
          :placeholder="t('document.search.kbPlaceholder')"
          clearable
          filterable
          style="width: 220px"
          @change="onSearch"
        >
          <el-option
            v-for="kb in kbOptions"
            :key="kb.id"
            :label="kb.name"
            :value="kb.id"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('document.field.status')">
        <el-select
          v-model="form.status_filter"
          :placeholder="t('document.search.statusPlaceholder')"
          clearable
          style="width: 180px"
        >
          <el-option :label="t('document.status.pending')" value="pending" />
          <el-option
            :label="t('document.status.processing')"
            value="processing"
          />
          <el-option
            :label="t('document.status.completed')"
            value="completed"
          />
          <el-option :label="t('document.status.failed')" value="failed" />
        </el-select>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="onSearch">{{
          t("buttons.search")
        }}</el-button>
        <el-button @click="resetForm">{{ t("buttons.reset") }}</el-button>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('document.title')"
      :columns="columns"
      @refresh="fetchList"
    >
      <template #buttons>
        <el-button
          v-auth="'document:add'"
          type="primary"
          :disabled="!form.kb_id"
          @click="openAddDialog"
        >
          {{ t("document.action.add") }}
        </el-button>
      </template>

      <template v-slot="{ size, dynamicColumns }">
        <pure-table
          :data="dataList"
          :columns="dynamicColumns"
          :loading="loading"
          :pagination="pagination"
          :size="size"
          row-key="id"
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <template #operation="{ row }">
            <el-button
              v-auth="'document:list'"
              link
              type="primary"
              @click="openDetail(row)"
            >
              {{ t("buttons.view") }}
            </el-button>
            <el-button
              v-auth="'document:list'"
              link
              type="primary"
              :disabled="!row.chunk_count"
              @click="openChunkView(row)"
            >
              {{ t("document.chunk.viewButton") }}
            </el-button>
            <el-button
              v-auth="'document:edit'"
              link
              type="primary"
              @click="openUpdateDialog(row)"
            >
              {{ t("document.action.reupload") }}
            </el-button>
            <el-popconfirm
              :title="t('document.action.deleteConfirm')"
              @confirm="handleDelete(row)"
            >
              <template #reference>
                <el-button v-auth="'document:delete'" link type="danger">
                  {{ t("buttons.delete") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <!-- Upload / re-upload dialog -->
    <el-dialog
      v-model="uploadVisible"
      :title="
        uploadMode === 'add'
          ? t('document.dialog.addTitle')
          : t('document.dialog.updateTitle')
      "
      width="520px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item :label="t('document.field.file')" required>
          <el-upload
            drag
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
          >
            <template #default>
              <div class="upload-hint">{{ t("document.dialog.dragHint") }}</div>
            </template>
          </el-upload>
        </el-form-item>
        <el-form-item :label="t('document.field.metadata')">
          <el-input
            v-model="uploadForm.metadataText"
            type="textarea"
            :rows="5"
            :placeholder="t('document.dialog.metadataPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button type="primary" @click="submitUpload">{{
          t("buttons.submit")
        }}</el-button>
      </template>
    </el-dialog>

    <!-- Detail dialog -->
    <el-dialog
      v-model="detailVisible"
      :title="t('document.dialog.detailTitle')"
      width="560px"
    >
      <el-descriptions v-if="detailRow" :column="2" border>
        <el-descriptions-item :label="t('document.field.id')">{{
          detailRow.id
        }}</el-descriptions-item>
        <el-descriptions-item :label="t('form.kbName.label')">{{
          detailRow.kb_id
        }}</el-descriptions-item>
        <el-descriptions-item :label="t('document.field.filename')" :span="2">
          {{ detailRow.filename }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('document.field.mimeType')">{{
          detailRow.mime_type
        }}</el-descriptions-item>
        <el-descriptions-item :label="t('document.field.storageType')">{{
          detailRow.storage_type
        }}</el-descriptions-item>
        <el-descriptions-item :label="t('document.field.chunkCount')">{{
          detailRow.chunk_count
        }}</el-descriptions-item>
        <el-descriptions-item :label="t('document.field.status')" :span="2">
          {{ t(`document.status.${detailRow.status}`) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('document.field.fileUri')" :span="2">
          {{ detailRow.file_uri || "-" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('document.field.hashValue')" :span="2">
          {{ detailRow.hash_value }}
        </el-descriptions-item>
        <el-descriptions-item
          v-if="detailRow.error_message"
          :label="t('document.field.errorMessage')"
          :span="2"
        >
          {{ detailRow.error_message }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <ProgressDialog :model-value="progress" @close="closeProgressDialog" />
    <ChunkViewDialog v-model="chunkVisible" :doc="chunkDoc" />
  </div>
</template>

<style scoped>
.search-form {
  padding: 18px 18px 0;
}

.upload-hint {
  padding: 24px 0;
  color: var(--el-text-color-secondary);
}
</style>
