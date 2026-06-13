<template>
  <div class="main">
    <!-- ── 搜索栏 ─────────────────────────────────────────────── -->
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('form.name')" prop="name">
        <el-input
          v-model="searchForm.name"
          :placeholder="t('knowledgeBase.search.namePlaceholder')"
          clearable
          class="w-50!"
          @keyup.enter="onSearch"
        />
      </el-form-item>

      <el-form-item :label="t('knowledgeBase.columns.domain')" prop="domain_id">
        <el-select
          v-model="searchForm.domain_id"
          :placeholder="t('knowledgeBase.search.domainPlaceholder')"
          clearable
          class="w-45!"
        >
          <el-option
            v-for="opt in domainOptions"
            :key="opt.id"
            :label="opt.name"
            :value="opt.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('labels.isActive')" prop="is_active">
        <el-select
          v-model="searchForm.is_active"
          :placeholder="t('search.status.selectPlaceholder')"
          clearable
          class="w-35!"
        >
          <el-option :label="t('labels.activated')" :value="true" />
          <el-option :label="t('labels.deactivated')" :value="false" />
        </el-select>
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

    <!-- ── 表格主体 ────────────────────────────────────────────── -->
    <PureTableBar
      :title="t('knowledgeBase.title')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button
          v-auth="'knowledge_base:add'"
          type="primary"
          :icon="Plus"
          @click="openCreate"
        >
          {{ t("buttons.add") }}
        </el-button>
      </template>

      <template v-slot="{ size, dynamicColumns }">
        <pure-table
          ref="tableRef"
          row-key="id"
          adaptive
          :adaptiveConfig="{ offsetBottom: 108 }"
          align-whole="center"
          :size="size"
          :data="tableData"
          :columns="dynamicColumns"
          :loading="loading"
          :pagination="pagination"
          :paginationSmall="size === 'small'"
          @page-size-change="onPageSizeChange"
          @page-current-change="onPageChange"
        >
          <!-- 状态列 -->
          <template #isActive="{ row }">
            <el-tag
              :type="row.is_active ? 'success' : 'info'"
              effect="plain"
              size="small"
            >
              {{
                row.is_active ? t("labels.activated") : t("labels.deactivated")
              }}
            </el-tag>
          </template>

          <!-- 文档 / 分块数 -->
          <template #documentCount="{ row }">
            <span class="font-medium text-blue-500">{{
              row.document_count
            }}</span>
          </template>
          <template #chunkCount="{ row }">
            <span class="font-medium text-violet-500">{{
              row.chunk_count
            }}</span>
          </template>

          <!-- 操作列 -->
          <template #operation="{ row }">
            <el-button
              v-auth="'knowledge_base:list'"
              link
              type="primary"
              size="small"
              :icon="DataAnalysis"
              @click="openStats(row)"
            >
              {{ t("buttons.stats") }}
            </el-button>

            <el-button
              v-auth="'knowledge_base:edit'"
              link
              type="primary"
              size="small"
              :icon="EditPen"
              @click="openEdit(row)"
            >
              {{ t("buttons.edit") }}
            </el-button>

            <el-button
              v-auth="'knowledge_base:edit'"
              link
              :type="row.is_active ? 'warning' : 'success'"
              size="small"
              :icon="row.is_active ? VideoPause : VideoPlay"
              @click="onToggle(row)"
            >
              {{ t("buttons.toggle") }}
            </el-button>

            <el-popconfirm
              :title="t('messages.deleteConfirm', { name: row.name })"
              @confirm="onDelete(row)"
            >
              <template #reference>
                <el-button
                  v-auth="'knowledge_base:delete'"
                  link
                  type="danger"
                  size="small"
                  :icon="Delete"
                >
                  {{ t("buttons.delete") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <!-- ── 新增 / 编辑 对话框 ─────────────────────────────────── -->
    <el-dialog
      v-model="dialogVisible"
      :title="
        isEdit
          ? t('knowledgeBase.dialog.editTitle')
          : t('knowledgeBase.dialog.createTitle')
      "
      width="720px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form
        ref="kbFormRef"
        :model="kbForm"
        :rules="formRules"
        label-width="120px"
        label-position="right"
      >
        <!-- 基本信息 -->
        <el-divider content-position="left">
          <span class="text-sm font-semibold text-gray-500">
            {{ t("knowledgeBase.form.basicInfo") }}
          </span>
        </el-divider>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('form.name.label')" prop="name">
              <el-input
                v-model="kbForm.name"
                :placeholder="t('form.name.placeholder')"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="t('knowledgeBase.form.domain')"
              prop="domain_id"
            >
              <el-select
                v-model="kbForm.domain_id"
                :placeholder="t('knowledgeBase.form.domainPlaceholder')"
                class="w-full"
              >
                <el-option
                  v-for="opt in domainOptions"
                  :key="opt.id"
                  :label="opt.name"
                  :value="opt.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item
          :label="t('knowledgeBase.form.collectionName')"
          prop="collection_name"
        >
          <el-input
            v-model="kbForm.collection_name"
            :placeholder="t('knowledgeBase.form.collectionNamePlaceholder')"
            :disabled="isEdit"
          />
        </el-form-item>

        <el-form-item :label="t('form.description')">
          <el-input
            v-model="kbForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('form.description.placeholder')"
          />
        </el-form-item>

        <el-form-item :label="t('knowledgeBase.form.keywords')">
          <el-select
            v-model="kbForm.keywords"
            multiple
            filterable
            allow-create
            default-first-option
            :placeholder="t('knowledgeBase.form.keywordsPlaceholder')"
            class="w-full"
          />
        </el-form-item>

        <!-- 向量配置 -->
        <el-divider content-position="left">
          <span class="text-sm font-semibold text-gray-500">
            {{ t("knowledgeBase.form.vectorConfig") }}
          </span>
        </el-divider>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('knowledgeBase.form.embeddingId')">
              <el-input-number
                v-model="kbForm.embedding_id"
                :placeholder="t('knowledgeBase.form.embeddingIdPlaceholder')"
                :min="1"
                controls-position="right"
                class="w-full"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('knowledgeBase.form.llmId')">
              <el-input-number
                v-model="kbForm.llm_id"
                :placeholder="t('knowledgeBase.form.llmIdPlaceholder')"
                :min="1"
                controls-position="right"
                class="w-full"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <!-- 分块配置 -->
        <el-divider content-position="left">
          <span class="text-sm font-semibold text-gray-500">
            {{ t("knowledgeBase.form.chunkConfig") }}
          </span>
        </el-divider>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('knowledgeBase.form.chunkSize')">
              <el-input-number
                v-model="kbForm.chunk_size"
                :min="1"
                controls-position="right"
                class="w-full"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('knowledgeBase.form.chunkOverlap')">
              <el-input-number
                v-model="kbForm.chunk_overlap"
                :min="0"
                controls-position="right"
                class="w-full"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('knowledgeBase.form.parentSize')">
              <el-input-number
                v-model="kbForm.parent_size"
                :min="1"
                controls-position="right"
                class="w-full"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('knowledgeBase.form.parentOverlap')">
              <el-input-number
                v-model="kbForm.parent_overlap"
                :min="0"
                controls-position="right"
                class="w-full"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item :label="t('labels.isActive')">
          <el-switch
            v-model="kbForm.is_active"
            :active-text="t('labels.activated')"
            :inactive-text="t('labels.deactivated')"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t("buttons.cancel") }}
        </el-button>
        <el-button type="primary" :loading="submitLoading" @click="onSubmit">
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>

    <!-- ── 统计对话框 ─────────────────────────────────────────── -->
    <el-dialog
      v-model="statsVisible"
      :title="t('knowledgeBase.dialog.statsTitle')"
      width="480px"
      destroy-on-close
    >
      <div v-if="statsData" class="stats-grid">
        <div class="stats-item">
          <div class="stats-label">
            {{ t("knowledgeBase.stats.documentCount") }}
          </div>
          <div class="stats-value text-blue-500">
            {{ statsData.document_count }}
          </div>
        </div>
        <div class="stats-item">
          <div class="stats-label">
            {{ t("knowledgeBase.stats.chunkCount") }}
          </div>
          <div class="stats-value text-violet-500">
            {{ statsData.chunk_count }}
          </div>
        </div>
        <div class="stats-item">
          <div class="stats-label">{{ t("labels.status") }}</div>
          <div class="stats-value">
            <el-tag
              :type="statsData.is_active ? 'success' : 'info'"
              effect="plain"
              size="small"
            >
              {{
                statsData.is_active
                  ? t("labels.activated")
                  : t("labels.deactivated")
              }}
            </el-tag>
          </div>
        </div>
        <div class="stats-item col-span-2">
          <div class="stats-label">
            {{ t("form.createdAt") }}
          </div>
          <div class="stats-value text-sm">
            {{ formatDate(statsData.created_at) }}
          </div>
        </div>
        <div class="stats-item col-span-2">
          <div class="stats-label">
            {{ t("form.updatedAt") }}
          </div>
          <div class="stats-value text-sm">
            {{ formatDate(statsData.updated_at) }}
          </div>
        </div>
      </div>
      <el-skeleton v-else :rows="4" animated />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import { message } from "@/utils/message";
import { PureTableBar } from "@/components/RePureTableBar";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";
import DataAnalysis from "~icons/ep/data-analysis"
import VideoPause from "~icons/ep/video-pause"
import VideoPlay from "~icons/ep/video-play"
import type { FormInstance, FormRules } from "element-plus";
import type { PaginationProps } from "@pureadmin/table";

import {
  getKnowledgeBaseList,
  getKnowledgeBaseStats,
  createKnowledgeBase,
  updateKnowledgeBase,
  deleteKnowledgeBase,
  toggleKnowledgeBase,
  type KnowledgeBaseItem,
  type KbCreatePayload,
  type KnowledgeBaseStats
} from "@/api/knowledge_base";

// ─── i18n ────────────────────────────────────────────────────────────────────

const { t } = useI18n();

// ─── 表格列定义 ───────────────────────────────────────────────────────────────

const columns: TableColumnList = [
  { type: "index", width: 60, fixed: "left" },
  {
    label: t("form.name"),
    prop: "name",
    minWidth: 160,
    showOverflowTooltip: true
  },
  {
    label: t("knowledgeBase.columns.domain"),
    prop: "domain_id",
    width: 100
  },
  {
    label: t("knowledgeBase.columns.collectionName"),
    prop: "collection_name",
    minWidth: 160,
    showOverflowTooltip: true
  },
  {
    label: t("knowledgeBase.columns.documentCount"),
    prop: "document_count",
    slot: "documentCount",
    width: 90
  },
  {
    label: t("knowledgeBase.columns.chunkCount"),
    prop: "chunk_count",
    slot: "chunkCount",
    width: 90
  },
  {
    label: t("labels.isActive"),
    prop: "is_active",
    slot: "isActive",
    width: 100
  },
  {
    label: t("form.updatedAt"),
    prop: "updated_at",
    formatter: ({ updated_at }) => formatDate(updated_at),
    width: 160
  },
  {
    label: t("labels.operation"),
    fixed: "right",
    width: 260,
    slot: "operation"
  }
];

// ─── 搜索表单 ─────────────────────────────────────────────────────────────────

const searchFormRef = ref<FormInstance>();
const searchForm = reactive<{
  name?: string;
  domain_id?: number;
  is_active?: boolean;
}>({});

// ─── 分页 & 数据 ─────────────────────────────────────────────────────────────

const loading = ref(false);
const tableData = ref<KnowledgeBaseItem[]>([]);
const pagination = reactive<PaginationProps>({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  pageSizes: [10, 20, 50],
  background: true
});

async function fetchList() {
  loading.value = true;
  try {
    const res = await getKnowledgeBaseList({
      name: searchForm.name || undefined,
      domain_id: searchForm.domain_id,
      is_active: searchForm.is_active,
      page: pagination.currentPage,
      page_size: pagination.pageSize
    });
    tableData.value = res.items;
    pagination.total = res.total;
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pagination.currentPage = 1;
  fetchList();
}

function onReset() {
  searchFormRef.value?.resetFields();
  searchForm.name = undefined;
  searchForm.domain_id = undefined;
  searchForm.is_active = undefined;
  onSearch();
}

function onPageChange(page: number) {
  pagination.currentPage = page;
  fetchList();
}

function onPageSizeChange(size: number) {
  pagination.pageSize = size;
  pagination.currentPage = 1;
  fetchList();
}

// ─── Domain 选项（实际项目替换为真实 API） ────────────────────────────────────

const domainOptions = ref<{ id: number; name: string }[]>([]);

async function fetchDomainOptions() {
  // TODO: replace with actual domain options API
  // const res = await getDomainOptions();
  // domainOptions.value = res.data.data;
}

// ─── 新增 / 编辑 ─────────────────────────────────────────────────────────────

const dialogVisible = ref(false);
const isEdit = ref(false);
const submitLoading = ref(false);
const kbFormRef = ref<FormInstance>();
let editId = 0;

const defaultForm = (): KbCreatePayload => ({
  name: "",
  domain_id: undefined as unknown as number,
  collection_name: "",
  description: undefined,
  keywords: [],
  embedding_id: undefined,
  llm_id: undefined,
  chunk_size: 400,
  chunk_overlap: 80,
  parent_size: 1800,
  parent_overlap: 200,
  is_active: true
});

const kbForm = reactive<KbCreatePayload>(defaultForm());

const formRules = computed<FormRules>(() => ({
  name: [
    {
      required: true,
      message: t("validation.required"),
      trigger: "blur"
    }
  ],
  domain_id: [
    {
      required: true,
      message: t("validation.required"),
      trigger: "change"
    }
  ],
  collection_name: [
    {
      required: true,
      message: t("validation.required"),
      trigger: "blur"
    }
  ]
}));

function openCreate() {
  isEdit.value = false;
  Object.assign(kbForm, defaultForm());
  dialogVisible.value = true;
}

function openEdit(row: KnowledgeBaseItem) {
  isEdit.value = true;
  editId = row.id;
  Object.assign(kbForm, {
    name: row.name,
    domain_id: row.domain_id,
    collection_name: row.collection_name,
    description: row.description ?? undefined,
    keywords: row.keywords ?? [],
    embedding_id: row.embedding_id ?? undefined,
    llm_id: row.llm_id ?? undefined,
    chunk_size: row.chunk_size,
    chunk_overlap: row.chunk_overlap,
    parent_size: row.parent_size,
    parent_overlap: row.parent_overlap,
    is_active: row.is_active
  });
  dialogVisible.value = true;
}

async function onSubmit() {
  await kbFormRef.value?.validate();
  submitLoading.value = true;
  try {
    if (isEdit.value) {
      await updateKnowledgeBase(editId, kbForm);
      message(t("messages.editSuccess"), { type: "success" });
    } else {
      await createKnowledgeBase(kbForm);
      message(t("messages.addSuccess"), { type: "success" });
    }
    dialogVisible.value = false;
    fetchList();
  } finally {
    submitLoading.value = false;
  }
}

// ─── 删除 ────────────────────────────────────────────────────────────────────

async function onDelete(row: KnowledgeBaseItem) {
  await deleteKnowledgeBase(row.id);
  message(t("messages.deleteSuccess"), { type: "success" });
  fetchList();
}

// ─── 切换状态 ─────────────────────────────────────────────────────────────────

async function onToggle(row: KnowledgeBaseItem) {
  await toggleKnowledgeBase(row.id);
  message(t("messages.toggleSuccess"), { type: "success" });
  fetchList();
}

// ─── 统计 ────────────────────────────────────────────────────────────────────

const statsVisible = ref(false);
const statsData = ref<KnowledgeBaseStats | null>(null);

async function openStats(row: KnowledgeBaseItem) {
  statsData.value = null;
  statsVisible.value = true;
  const res = await getKnowledgeBaseStats(row.id);
  statsData.value = res;
}

// ─── 工具 ────────────────────────────────────────────────────────────────────

function formatDate(dateStr: string) {
  if (!dateStr) return "-";
  return new Date(dateStr).toLocaleString();
}

// ─── Init ────────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchDomainOptions();
  fetchList();
});
</script>

<style scoped lang="scss">
.search-form {
  :deep(.el-form-item) {
    margin-bottom: 12px;
  }
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  padding: 8px 0;
}

.stats-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  border-radius: 8px;

  &.col-span-2 {
    grid-column: span 2;
  }
}

.stats-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.stats-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
