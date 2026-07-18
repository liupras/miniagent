<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('promptManagement.keyword')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          :placeholder="t('promptManagement.keywordPlaceholder')"
          clearable
          class="w-60!"
          @keyup.enter="onSearch"
        />
      </el-form-item>
      <el-form-item :label="t('promptManagement.language')" prop="lang">
        <el-select
          v-model="searchForm.lang"
          :placeholder="t('promptManagement.allLanguages')"
          clearable
          filterable
          class="w-40!"
        >
          <el-option
            v-for="lang in languageOptions"
            :key="lang"
            :label="lang"
            :value="lang"
          />
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

    <PureTableBar
      :title="t('promptManagement.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #buttons>
        <el-button
          v-if="hasPerms('prompt:add')"
          type="primary"
          :icon="Plus"
          @click="openEditor('add')"
        >
          {{ t("buttons.add") }}
        </el-button>
      </template>
      <template #default="{ size, dynamicColumns }">
        <pure-table
          row-key="id"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :pagination="pagination"
          :paginationSmall="true"
          align-whole="center"
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <template #key="{ row }">
            <code class="text-sm">{{ row.key }}</code>
          </template>
          <template #lang="{ row }">
            <el-tag :type="languageTagType(row.lang)" effect="plain">
              {{ row.lang }}
            </el-tag>
          </template>
          <template #value="{ row }">
            <button
              class="prompt-preview"
              type="button"
              @click="openPreview(row)"
            >
              {{ row.value || t("promptManagement.emptyValue") }}
            </button>
          </template>
          <template #variables="{ row }">
            <el-tooltip
              v-if="extractVariables(row.value).length"
              :content="extractVariables(row.value).join(', ')"
            >
              <div class="flex flex-wrap justify-center gap-1">
                <el-tag
                  v-for="variable in extractVariables(row.value).slice(0, 2)"
                  :key="variable"
                  size="small"
                  type="warning"
                  effect="plain"
                >
                  {{ variable }}
                </el-tag>
                <el-tag
                  v-if="extractVariables(row.value).length > 2"
                  size="small"
                  type="warning"
                >
                  +{{ extractVariables(row.value).length - 2 }}
                </el-tag>
              </div>
            </el-tooltip>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template #operation="{ row }">
            <el-button
              type="primary"
              link
              :icon="View"
              @click="openPreview(row)"
            >
              {{ t("buttons.view") }}
            </el-button>
            <el-button
              v-if="hasPerms('prompt:edit')"
              type="primary"
              link
              :icon="EditPen"
              @click="openEditor('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-popconfirm
              :title="
                t('messages.deleteConfirm', {
                  name: `${row.key} [${row.lang}]`
                })
              "
              @confirm="removePrompt(row)"
            >
              <template #reference>
                <el-button
                  v-if="hasPerms('prompt:delete')"
                  type="danger"
                  link
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

    <el-dialog
      v-model="previewVisible"
      :title="
        currentPrompt ? `${currentPrompt.key} [${currentPrompt.lang}]` : ''
      "
      width="820px"
      destroy-on-close
    >
      <el-descriptions v-if="currentPrompt" :column="1" border>
        <el-descriptions-item :label="t('promptManagement.description')">
          {{ currentPrompt.description || "-" }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('promptManagement.variables')">
          <div
            v-if="extractVariables(currentPrompt.value).length"
            class="flex gap-1"
          >
            <el-tag
              v-for="variable in extractVariables(currentPrompt.value)"
              :key="variable"
              size="small"
              type="warning"
              effect="plain"
            >
              {{ variable }}
            </el-tag>
          </div>
          <span v-else>-</span>
        </el-descriptions-item>
      </el-descriptions>
      <el-scrollbar max-height="55vh" class="prompt-content mt-4">
        <pre>{{ currentPrompt?.value }}</pre>
      </el-scrollbar>
      <template #footer>
        <el-button :icon="CopyDocument" @click="copyCurrentPrompt">
          {{ t("promptManagement.copy") }}
        </el-button>
        <el-button @click="previewVisible = false">
          {{ t("buttons.close") }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="editorVisible"
      :title="
        editorType === 'add'
          ? t('promptManagement.add')
          : t('promptManagement.edit')
      "
      width="900px"
      destroy-on-close
    >
      <el-alert
        v-if="editorType === 'edit'"
        :title="t('promptManagement.identityHint')"
        type="info"
        show-icon
        :closable="false"
        class="mb-4"
      />
      <el-form
        ref="editorFormRef"
        :model="editorForm"
        :rules="editorRules"
        label-width="110px"
      >
        <div class="grid grid-cols-2 gap-x-4">
          <el-form-item :label="t('promptManagement.key')" prop="key">
            <el-input
              v-model="editorForm.key"
              maxlength="200"
              :disabled="editorType === 'edit'"
              :placeholder="t('promptManagement.keyPlaceholder')"
            />
          </el-form-item>
          <el-form-item :label="t('promptManagement.language')" prop="lang">
            <el-select
              v-model="editorForm.lang"
              filterable
              allow-create
              default-first-option
              class="w-full"
              :disabled="editorType === 'edit'"
              :placeholder="t('promptManagement.languagePlaceholder')"
            >
              <el-option
                v-for="lang in languageOptions"
                :key="lang"
                :label="lang"
                :value="lang"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item
          :label="t('promptManagement.description')"
          prop="description"
        >
          <el-input
            v-model="editorForm.description"
            maxlength="255"
            show-word-limit
            :placeholder="t('promptManagement.descriptionPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('promptManagement.value')" prop="value">
          <div class="w-full">
            <el-input
              v-model="editorForm.value"
              type="textarea"
              :rows="16"
              class="prompt-editor"
              :placeholder="t('promptManagement.valuePlaceholder')"
            />
            <div
              class="mt-2 flex flex-wrap items-center gap-1 text-xs text-gray-400"
            >
              <span>{{ t("promptManagement.detectedVariables") }}</span>
              <el-tag
                v-for="variable in extractVariables(editorForm.value)"
                :key="variable"
                size="small"
                type="warning"
                effect="plain"
              >
                {{ variable }}
              </el-tag>
              <span v-if="!extractVariables(editorForm.value).length">-</span>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">
          {{ t("buttons.cancel") }}
        </el-button>
        <el-button
          type="primary"
          :loading="editorLoading"
          @click="submitPrompt"
        >
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import dayjs from "dayjs";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import View from "~icons/ep/view";
import EditPen from "~icons/ep/edit-pen";
import Delete from "~icons/ep/delete";
import CopyDocument from "~icons/ep/copy-document";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasPerms } from "@/utils/auth";
import {
  createPrompt,
  deletePrompt,
  getPromptLanguages,
  getPromptList,
  updatePrompt,
  type PromptItem
} from "@/api/prompt";

defineOptions({ name: "PromptManagement" });

const { t } = useI18n();
const loading = ref(false);
const tableData = ref<PromptItem[]>([]);
const languageOptions = ref<string[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({ keyword: "", lang: "" });
const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper",
  pageSizes: [10, 20, 50, 100]
});

const formatTime = (value?: string | null) =>
  value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-";

function extractVariables(value: string): string[] {
  const variables = new Set<string>();
  const pattern = /\{([A-Za-z_][\w.]*)\}/g;
  for (const match of value.matchAll(pattern)) {
    const start = match.index ?? 0;
    const end = start + match[0].length;
    // Double braces are escaped literals used by str.format templates.
    if (value[start - 1] !== "{" && value[end] !== "}") {
      variables.add(match[1]);
    }
  }
  return [...variables];
}

function languageTagType(lang: string) {
  if (lang.toLowerCase().startsWith("zh")) return "success";
  if (lang.toLowerCase().startsWith("en")) return "primary";
  return "info";
}

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 70 },
  {
    label: t("promptManagement.key"),
    prop: "key",
    minWidth: 220,
    slot: "key"
  },
  {
    label: t("promptManagement.language"),
    prop: "lang",
    width: 100,
    slot: "lang"
  },
  {
    label: t("promptManagement.value"),
    prop: "value",
    minWidth: 260,
    slot: "value"
  },
  {
    label: t("promptManagement.variables"),
    prop: "variables",
    width: 150,
    slot: "variables"
  },
  {
    label: t("promptManagement.description"),
    prop: "description",
    minWidth: 180,
    showOverflowTooltip: true
  },
  {
    label: t("form.updatedAt"),
    prop: "updated_at",
    width: 165,
    formatter: ({ updated_at }) => formatTime(updated_at)
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 230,
    fixed: "right",
    slot: "operation"
  }
];

const previewVisible = ref(false);
const currentPrompt = ref<PromptItem>();

function openPreview(row: PromptItem) {
  currentPrompt.value = row;
  previewVisible.value = true;
}

async function copyCurrentPrompt() {
  if (!currentPrompt.value) return;
  try {
    await navigator.clipboard.writeText(currentPrompt.value.value);
    ElMessage.success(t("promptManagement.copySuccess"));
  } catch {
    ElMessage.error(t("promptManagement.copyFailed"));
  }
}

const editorVisible = ref(false);
const editorLoading = ref(false);
const editorType = ref<"add" | "edit">("add");
const editorFormRef = ref<FormInstance>();
const editorForm = reactive({
  key: "",
  lang: "zh_CN",
  value: "",
  description: ""
});

function normalizeLanguage(value: string) {
  const [language, region] = value.trim().replace("-", "_").split("_", 2);
  return region
    ? `${language.toLowerCase()}_${region.toUpperCase()}`
    : language.toLowerCase();
}

const editorRules: FormRules = {
  key: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ],
  lang: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "change"
    },
    {
      pattern: /^[A-Za-z]{2,3}(?:[-_][A-Za-z]{2,4})?$/,
      message: () => t("promptManagement.languageInvalid"),
      trigger: "change"
    }
  ]
};

function openEditor(type: "add" | "edit", row?: PromptItem) {
  editorType.value = type;
  Object.assign(
    editorForm,
    type === "edit" && row
      ? {
          key: row.key,
          lang: row.lang,
          value: row.value,
          description: row.description || ""
        }
      : { key: "", lang: "zh_CN", value: "", description: "" }
  );
  editorVisible.value = true;
}

async function fetchData() {
  loading.value = true;
  try {
    const result = await getPromptList({
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      keyword: searchForm.keyword.trim() || undefined,
      lang: searchForm.lang || undefined
    });
    tableData.value = result.data;
    pagination.total = result.total;
  } finally {
    loading.value = false;
  }
}

async function loadLanguages() {
  languageOptions.value = await getPromptLanguages();
}

function onSearch() {
  pagination.currentPage = 1;
  fetchData();
}

function onReset() {
  searchFormRef.value?.resetFields();
  Object.assign(searchForm, { keyword: "", lang: "" });
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

async function submitPrompt() {
  await editorFormRef.value?.validate();
  editorLoading.value = true;
  try {
    if (editorType.value === "add") {
      await createPrompt({
        key: editorForm.key.trim(),
        lang: normalizeLanguage(editorForm.lang),
        value: editorForm.value,
        description: editorForm.description.trim() || null
      });
      ElMessage.success(t("messages.addSuccess"));
    } else {
      await updatePrompt(editorForm.key, editorForm.lang, {
        value: editorForm.value,
        description: editorForm.description.trim() || null
      });
      ElMessage.success(t("messages.editSuccess"));
    }
    editorVisible.value = false;
    await Promise.all([fetchData(), loadLanguages()]);
  } finally {
    editorLoading.value = false;
  }
}

async function removePrompt(row: PromptItem) {
  await deletePrompt(row.key, row.lang);
  ElMessage.success(t("messages.deleteSuccess"));
  if (tableData.value.length === 1 && pagination.currentPage > 1) {
    pagination.currentPage--;
  }
  await Promise.all([fetchData(), loadLanguages()]);
}

onMounted(() => Promise.all([fetchData(), loadLanguages()]));
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.prompt-preview {
  display: -webkit-box;
  width: 100%;
  padding: 0;
  overflow: hidden;
  -webkit-line-clamp: 2;
  font: inherit;
  color: var(--el-color-primary);
  text-align: left;
  white-space: pre-wrap;
  cursor: pointer;
  background: none;
  border: 0;
  -webkit-box-orient: vertical;
}

.prompt-content {
  padding: 16px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
}

.prompt-content pre {
  margin: 0;
  font-family: Consolas, "Courier New", monospace;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}

.prompt-editor :deep(textarea) {
  font-family: Consolas, "Courier New", monospace;
  line-height: 1.5;
}

@media (width <= 920px) {
  :deep(.el-dialog) {
    width: 94% !important;
  }
}
</style>
