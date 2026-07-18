<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('llmManagement.provider')" prop="provider_name">
        <el-select
          v-model="searchForm.provider_name"
          :placeholder="t('llmManagement.allProviders')"
          clearable
          filterable
          class="w-45!"
        >
          <el-option
            v-for="provider in providerOptions"
            :key="provider"
            :label="provider"
            :value="provider"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('llmManagement.model')" prop="model_name">
        <el-input
          v-model="searchForm.model_name"
          :placeholder="t('llmManagement.modelSearchPlaceholder')"
          clearable
          class="w-52!"
          @keyup.enter="onSearch"
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
      :title="t('llmManagement.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #buttons>
        <el-button
          v-if="hasPerms('llm:add')"
          type="primary"
          :icon="Plus"
          @click="openDialog('add')"
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
          <template #provider="{ row }">
            <el-tag effect="plain">{{ row.provider_name }}</el-tag>
          </template>
          <template #model="{ row }">
            <div class="flex flex-col items-start">
              <span class="font-medium">{{ row.model_name }}</span>
              <span class="text-xs text-gray-400">{{ row.name }}</span>
            </div>
          </template>
          <template #capabilities="{ row }">
            <el-tooltip
              v-if="capabilityKeys(row).length"
              :content="formatCapabilities(row.capabilities)"
              placement="top"
            >
              <div class="flex max-w-55 flex-wrap justify-center gap-1">
                <el-tag
                  v-for="key in capabilityKeys(row).slice(0, 2)"
                  :key="key"
                  size="small"
                  type="info"
                  effect="plain"
                >
                  {{ key }}
                </el-tag>
                <el-tag
                  v-if="capabilityKeys(row).length > 2"
                  size="small"
                  type="info"
                >
                  +{{ capabilityKeys(row).length - 2 }}
                </el-tag>
              </div>
            </el-tooltip>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template #operation="{ row }">
            <el-button
              v-if="hasPerms('llm:edit')"
              type="primary"
              link
              :icon="EditPen"
              @click="openDialog('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-popconfirm
              :title="t('messages.deleteConfirm', { name: row.name })"
              @confirm="removeLLM(row)"
            >
              <template #reference>
                <el-button
                  v-if="hasPerms('llm:delete')"
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
      v-model="dialogVisible"
      :title="
        dialogType === 'add' ? t('llmManagement.add') : t('llmManagement.edit')
      "
      width="680px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="130px"
      >
        <el-form-item :label="t('llmManagement.displayName')" prop="name">
          <el-input
            v-model="dialogForm.name"
            maxlength="100"
            :placeholder="t('llmManagement.displayNamePlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('llmManagement.provider')" prop="provider_name">
          <el-select
            v-model="dialogForm.provider_name"
            filterable
            allow-create
            default-first-option
            class="w-full"
            :placeholder="t('llmManagement.providerPlaceholder')"
          >
            <el-option
              v-for="provider in providerOptions"
              :key="provider"
              :label="provider"
              :value="provider"
            />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('llmManagement.model')" prop="model_name">
          <el-input
            v-model="dialogForm.model_name"
            maxlength="100"
            :placeholder="t('llmManagement.modelPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('llmManagement.baseUrl')" prop="base_url">
          <el-input
            v-model="dialogForm.base_url"
            maxlength="1024"
            placeholder="https://api.example.com/v1"
          />
        </el-form-item>
        <el-form-item :label="t('llmManagement.apiKey')" prop="api_key">
          <div class="w-full">
            <el-input
              v-model="dialogForm.api_key"
              type="password"
              show-password
              maxlength="512"
              autocomplete="new-password"
              :disabled="clearApiKey"
              :placeholder="
                dialogType === 'edit'
                  ? t('llmManagement.apiKeyEditPlaceholder')
                  : t('llmManagement.apiKeyPlaceholder')
              "
            />
            <div
              v-if="dialogType === 'edit'"
              class="mt-2 flex items-center justify-between"
            >
              <span class="text-xs text-gray-400">
                {{ t("llmManagement.apiKeyEditHint") }}
              </span>
              <el-checkbox v-model="clearApiKey">
                {{ t("llmManagement.clearApiKey") }}
              </el-checkbox>
            </div>
          </div>
        </el-form-item>
        <div class="grid grid-cols-2 gap-x-4">
          <el-form-item
            :label="t('llmManagement.temperature')"
            prop="temperature"
          >
            <el-input-number
              v-model="dialogForm.temperature"
              :min="0"
              :max="2"
              :step="0.1"
              :precision="2"
              class="w-full!"
            />
          </el-form-item>
          <el-form-item :label="t('llmManagement.maxTokens')" prop="max_tokens">
            <el-input-number
              v-model="dialogForm.max_tokens"
              :min="1"
              :step="100"
              class="w-full!"
            />
          </el-form-item>
        </div>
        <el-form-item
          :label="t('llmManagement.capabilities')"
          prop="capabilitiesText"
        >
          <el-input
            v-model="dialogForm.capabilitiesText"
            type="textarea"
            :rows="6"
            class="json-editor"
            :placeholder="t('llmManagement.capabilitiesPlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t("buttons.cancel") }}
        </el-button>
        <el-button type="primary" :loading="dialogLoading" @click="submitLLM">
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import dayjs from "dayjs";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import EditPen from "~icons/ep/edit-pen";
import Delete from "~icons/ep/delete";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasPerms } from "@/utils/auth";
import {
  createLLM,
  deleteLLM,
  getLLMList,
  getLLMProviders,
  updateLLM,
  type LLMCapabilities,
  type LLMCreatePayload,
  type LLMItem,
  type LLMUpdatePayload
} from "@/api/llm";

defineOptions({ name: "LLMManagement" });

const { t } = useI18n();
const loading = ref(false);
const tableData = ref<LLMItem[]>([]);
const providerOptions = ref<string[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({
  provider_name: "",
  model_name: ""
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
  value ? dayjs(value).format("YYYY-MM-DD HH:mm") : "-";
const capabilityKeys = (row: LLMItem) =>
  row.capabilities ? Object.keys(row.capabilities) : [];
const formatCapabilities = (value?: LLMCapabilities | null) =>
  value ? JSON.stringify(value, null, 2) : "-";

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 70 },
  {
    label: t("llmManagement.provider"),
    prop: "provider_name",
    width: 130,
    slot: "provider"
  },
  {
    label: t("llmManagement.modelAndName"),
    prop: "model_name",
    minWidth: 180,
    slot: "model"
  },
  {
    label: t("llmManagement.baseUrl"),
    prop: "base_url",
    minWidth: 210,
    showOverflowTooltip: true
  },
  {
    label: t("llmManagement.temperature"),
    prop: "temperature",
    width: 100
  },
  {
    label: t("llmManagement.maxTokens"),
    prop: "max_tokens",
    width: 115
  },
  {
    label: t("llmManagement.capabilities"),
    prop: "capabilities",
    minWidth: 150,
    slot: "capabilities"
  },
  {
    label: t("form.createdAt"),
    prop: "created_at",
    width: 165,
    formatter: ({ created_at }) => formatTime(created_at)
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 160,
    fixed: "right",
    slot: "operation",
    hide: !hasPerms("llm:edit") && !hasPerms("llm:delete")
  }
];

const dialogVisible = ref(false);
const dialogLoading = ref(false);
const dialogType = ref<"add" | "edit">("add");
const dialogFormRef = ref<FormInstance>();
const clearApiKey = ref(false);
const dialogForm = reactive({
  id: undefined as number | undefined,
  name: "",
  provider_name: "",
  base_url: "",
  api_key: "",
  model_name: "",
  temperature: 0.7,
  max_tokens: 2000,
  capabilitiesText: ""
});

function parseCapabilities(value: string): LLMCapabilities | null {
  if (!value.trim()) return null;
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(t("llmManagement.capabilitiesObjectError"));
  }
  return parsed as LLMCapabilities;
}

const dialogRules: FormRules = {
  name: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ],
  provider_name: [
    {
      required: true,
      message: () => t("validation.required"),
      trigger: "change"
    }
  ],
  model_name: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ],
  base_url: [
    { required: true, message: () => t("validation.required"), trigger: "blur" }
  ],
  capabilitiesText: [
    {
      validator: (_rule, value: string, callback) => {
        try {
          parseCapabilities(value);
          callback();
        } catch (error) {
          callback(
            error instanceof Error
              ? error
              : new Error(t("llmManagement.capabilitiesJsonError"))
          );
        }
      },
      trigger: "blur"
    }
  ]
};

async function loadProviders() {
  providerOptions.value = await getLLMProviders();
}

async function fetchData() {
  loading.value = true;
  try {
    const result = await getLLMList({
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      provider_name: searchForm.provider_name || undefined,
      model_name: searchForm.model_name.trim() || undefined
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
  Object.assign(searchForm, { provider_name: "", model_name: "" });
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

function openDialog(type: "add" | "edit", row?: LLMItem) {
  dialogType.value = type;
  clearApiKey.value = false;
  Object.assign(
    dialogForm,
    type === "edit" && row
      ? {
          id: row.id,
          name: row.name,
          provider_name: row.provider_name,
          base_url: row.base_url,
          api_key: "",
          model_name: row.model_name,
          temperature: row.temperature,
          max_tokens: row.max_tokens,
          capabilitiesText: row.capabilities
            ? JSON.stringify(row.capabilities, null, 2)
            : ""
        }
      : {
          id: undefined,
          name: "",
          provider_name: "",
          base_url: "",
          api_key: "",
          model_name: "",
          temperature: 0.7,
          max_tokens: 2000,
          capabilitiesText: ""
        }
  );
  dialogVisible.value = true;
}

async function submitLLM() {
  await dialogFormRef.value?.validate();
  const commonPayload: LLMCreatePayload = {
    name: dialogForm.name.trim(),
    provider_name: dialogForm.provider_name.trim(),
    base_url: dialogForm.base_url.trim(),
    model_name: dialogForm.model_name.trim(),
    temperature: dialogForm.temperature,
    max_tokens: dialogForm.max_tokens,
    capabilities: parseCapabilities(dialogForm.capabilitiesText)
  };

  dialogLoading.value = true;
  try {
    if (dialogType.value === "add") {
      await createLLM({
        ...commonPayload,
        api_key: dialogForm.api_key.trim() || null
      });
      ElMessage.success(t("messages.addSuccess"));
    } else {
      const payload: LLMUpdatePayload = { ...commonPayload };
      if (clearApiKey.value) payload.api_key = null;
      else if (dialogForm.api_key.trim()) {
        payload.api_key = dialogForm.api_key.trim();
      }
      await updateLLM(dialogForm.id!, payload);
      ElMessage.success(t("messages.editSuccess"));
    }
    dialogVisible.value = false;
    await Promise.all([fetchData(), loadProviders()]);
  } finally {
    dialogLoading.value = false;
  }
}

async function removeLLM(row: LLMItem) {
  await deleteLLM(row.id);
  ElMessage.success(t("messages.deleteSuccess"));
  if (tableData.value.length === 1 && pagination.currentPage > 1) {
    pagination.currentPage--;
  }
  await Promise.all([fetchData(), loadProviders()]);
}

onMounted(() => Promise.all([fetchData(), loadProviders()]));
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.json-editor :deep(textarea) {
  font-family: Consolas, "Courier New", monospace;
}

@media (width <= 720px) {
  :deep(.el-dialog) {
    width: 94% !important;
  }
}
</style>
