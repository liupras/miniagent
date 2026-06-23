<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import {
  getDocumentChunks,
  type DocumentRead,
  type ParentChunkRead
} from "@/api/document";

const { t } = useI18n();

const props = defineProps<{
  modelValue: boolean;
  doc: DocumentRead | null;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
}>();

const loading = ref(false);
const totalParents = ref(0);
const totalChunks = ref(0);
const parentChunks = ref<ParentChunkRead[]>([]);
const activeNames = ref<number[]>([]);
const currentPage = ref(1);
const pageSize = ref(20);

async function fetchChunks() {
  if (!props.doc) return;
  loading.value = true;
  //console.log(props.doc.id);
  try {
    const res = await getDocumentChunks(
      props.doc.kb_id,
      props.doc.id,
      currentPage.value,
      pageSize.value
    );
    totalParents.value = res.total_parent_chunks;
    totalChunks.value = res.total_chunks;
    parentChunks.value = res.parent_chunks;
    activeNames.value = [];
  } catch {
    ElMessage.error(t("document.chunk.loadError"));
  } finally {
    loading.value = false;
  }
}

function handlePageChange(page: number) {
  currentPage.value = page;
  fetchChunks();
}

watch(
  () => props.modelValue,
  visible => {
    if (visible) {
      currentPage.value = 1;
      fetchChunks();
    } else {
      parentChunks.value = [];
    }
  }
);

function close() {
  emit("update:modelValue", false);
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('document.chunk.dialogTitle', { name: doc?.filename ?? '' })"
    width="900px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="chunk-view">
      <div class="chunk-summary">
        <el-tag type="info">
          {{ t("document.chunk.parentCount", { count: totalParents }) }}
        </el-tag>
        <el-tag type="success" class="ml-2">
          {{ t("document.chunk.chunkCount", { count: totalChunks }) }}
        </el-tag>
      </div>

      <el-empty
        v-if="!loading && parentChunks.length === 0"
        :description="t('document.chunk.empty')"
      />

      <el-collapse v-else v-model="activeNames" class="chunk-collapse">
        <el-collapse-item
          v-for="parent in parentChunks"
          :key="parent.id"
          :name="parent.id"
        >
          <template #title>
            <div class="parent-title">
              <span class="parent-index">
                {{
                  t("document.chunk.parentLabel", { index: parent.chunk_index })
                }}
              </span>
              <span class="parent-meta">
                {{ t("document.chunk.charCount") }}: {{ parent.char_count }} ·
                {{ t("document.chunk.tokenCount") }}: {{ parent.token_count }} ·
                {{
                  t("document.chunk.childCount", {
                    count: parent.chunks.length
                  })
                }}
              </span>
            </div>
          </template>

          <div class="parent-text">{{ parent.text }}</div>

          <el-table
            v-if="parent.chunks.length"
            :data="parent.chunks"
            size="small"
            border
            class="chunk-sub-table"
          >
            <el-table-column
              prop="chunk_index"
              :label="t('document.chunk.indexLabel')"
              width="70"
            />
            <el-table-column
              prop="char_count"
              :label="t('document.chunk.charCount')"
              width="90"
            />
            <el-table-column
              prop="token_count"
              :label="t('document.chunk.tokenCount')"
              width="90"
            />
            <el-table-column prop="text" :label="t('document.chunk.textLabel')">
              <template #default="{ row }">
                <div class="chunk-text">{{ row.text }}</div>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>

      <el-pagination
        v-if="totalParents > pageSize"
        class="chunk-pagination"
        :current-page="currentPage"
        :page-size="pageSize"
        :total="totalParents"
        layout="prev, pager, next"
        @current-change="handlePageChange"
      />
    </div>

    <template #footer>
      <el-button @click="close">{{ t("buttons.close") }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.chunk-summary {
  margin-bottom: 12px;
}

.chunk-collapse {
  max-height: 55vh;
  overflow-y: auto;
}

.parent-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.parent-index {
  font-weight: 600;
}

.parent-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.parent-text {
  padding: 8px 12px;
  margin-bottom: 10px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  background-color: var(--el-fill-color-light);
  border-radius: 4px;
  max-height: 160px;
}

.chunk-text {
  overflow-y: auto;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  max-height: 100px;
}

.chunk-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
