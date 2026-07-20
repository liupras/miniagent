<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('embeddingManagement.name')" prop="name">
        <el-select
          v-model="searchForm.name"
          :placeholder="t('embeddingManagement.allNames')"
          clearable
          filterable
          class="w-52!"
        >
          <el-option
            v-for="option in embeddingOptions"
            :key="option.id"
            :label="option.name"
            :value="option.name"
          />
        </el-select>
      </el-form-item>
      <el-form-item
        :label="t('embeddingManagement.provider')"
        prop="provider_name"
      >
        <el-input
          v-model="searchForm.provider_name"
          :placeholder="t('embeddingManagement.providerSearchPlaceholder')"
          clearable
          class="w-45!"
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
      :title="t('embeddingManagement.title')"
      :columns="columns"
      @refresh="fetchData"
    >
      <template #buttons>
        <el-button
          v-if="hasPerms('embedding:add')"
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
          <template #apiKey="{ row }">
            <el-tag :type="row.api_key ? 'success' : 'info'" size="small">
              {{
                row.api_key
                  ? t("embeddingManagement.configured")
                  : t("embeddingManagement.notConfigured")
              }}
            </el-tag>
          </template>
          <template #operation="{ row }">
            <el-button
              v-if="hasPerms('embedding:edit')"
              type="primary"
              link
              :icon="EditPen"
              @click="openDialog('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-popconfirm
              :title="t('messages.deleteConfirm', { name: row.name })"
              @confirm="removeEmbedding(row)"
            >
              <template #reference>
                <el-button
                  v-if="hasPerms('embedding:delete')"
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
        dialogType === 'add'
          ? t('embeddingManagement.add')
          : t('embeddingManagement.edit')
      "
      width="620px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="130px"
      >
        <el-form-item :label="t('embeddingManagement.name')" prop="name">
          <el-input
            v-model="dialogForm.name"
            maxlength="100"
            :placeholder="t('embeddingManagement.namePlaceholder')"
          />
        </el-form-item>
        <el-form-item
          :label="t('embeddingManagement.provider')"
          prop="provider_name"
        >
          <el-input
            v-model="dialogForm.provider_name"
            maxlength="50"
            :placeholder="t('embeddingManagement.providerPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('embeddingManagement.model')" prop="model_name">
          <el-input
            v-model="dialogForm.model_name"
            maxlength="100"
            :placeholder="t('embeddingManagement.modelPlaceholder')"
          />
        </el-form-item>
        <el-form-item :label="t('embeddingManagement.baseUrl')" prop="base_url">
          <el-input
            v-model="dialogForm.base_url"
            maxlength="1024"
            placeholder="https://api.example.com/v1"
          />
        </el-form-item>
        <el-form-item :label="t('embeddingManagement.apiKey')" prop="api_key">
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
                  ? t('embeddingManagement.apiKeyEditPlaceholder')
                  : t('embeddingManagement.apiKeyPlaceholder')
              "
            />
            <div
              v-if="dialogType === 'edit'"
              class="mt-2 flex items-center justify-between"
            >
              <span class="text-xs text-gray-400">
                {{ t("embeddingManagement.apiKeyEditHint") }}
              </span>
              <el-checkbox v-model="clearApiKey">
                {{ t("embeddingManagement.clearApiKey") }}
              </el-checkbox>
            </div>
          </div>
        </el-form-item>
        <el-form-item
          :label="t('embeddingManagement.maxTokens')"
          prop="max_tokens"
        >
          <el-input-number
            v-model="dialogForm.max_tokens"
            :min="1"
            :step="128"
            class="w-full!"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t("buttons.cancel") }}
        </el-button>
        <el-button
          type="primary"
          :loading="dialogLoading"
          @click="submitEmbedding"
        >
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useQuickAction } from "@/utils/quickAction";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import EditPen from "~icons/ep/edit-pen";
import Delete from "~icons/ep/delete";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasPerms } from "@/utils/auth";
import {
  createEmbedding,
  deleteEmbedding,
  getEmbeddingList,
  getEmbeddingOptions,
  updateEmbedding,
  type EmbeddingItem,
  type EmbeddingOption,
  type EmbeddingPayload
} from "@/api/embedding";

defineOptions({ name: "EmbeddingManagement" });

const { t } = useI18n();
const loading = ref(false);
const tableData = ref<EmbeddingItem[]>([]);
const embeddingOptions = ref<EmbeddingOption[]>([]);
const searchFormRef = ref<FormInstance>();
const searchForm = reactive({ name: "", provider_name: "" });
const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper",
  pageSizes: [10, 20, 50, 100]
});

const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 70 },
  {
    label: t("embeddingManagement.provider"),
    prop: "provider_name",
    width: 140,
    slot: "provider"
  },
  {
    label: t("embeddingManagement.modelAndName"),
    prop: "model_name",
    minWidth: 190,
    slot: "model"
  },
  {
    label: t("embeddingManagement.baseUrl"),
    prop: "base_url",
    minWidth: 230,
    showOverflowTooltip: true
  },
  {
    label: t("embeddingManagement.maxTokens"),
    prop: "max_tokens",
    width: 125
  },
  {
    label: t("embeddingManagement.apiKeyStatus"),
    prop: "api_key",
    width: 120,
    slot: "apiKey"
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 160,
    fixed: "right",
    slot: "operation",
    hide: !hasPerms("embedding:edit") && !hasPerms("embedding:delete")
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
  max_tokens: 512
});

const requiredRule = {
  required: true,
  message: () => t("validation.required"),
  trigger: "blur"
};
const dialogRules: FormRules = {
  name: [requiredRule],
  provider_name: [requiredRule],
  model_name: [requiredRule],
  base_url: [requiredRule]
};

async function fetchData() {
  loading.value = true;
  try {
    const result = await getEmbeddingList({
      name: searchForm.name || undefined,
      provider_name: searchForm.provider_name.trim() || undefined,
      page: pagination.currentPage,
      page_size: pagination.pageSize
    });
    tableData.value = result.items;
    pagination.total = result.total;
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  embeddingOptions.value = await getEmbeddingOptions();
}

function onSearch() {
  pagination.currentPage = 1;
  fetchData();
}

function onReset() {
  searchFormRef.value?.resetFields();
  Object.assign(searchForm, { name: "", provider_name: "" });
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

function openDialog(type: "add" | "edit", row?: EmbeddingItem) {
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
          max_tokens: row.max_tokens
        }
      : {
          id: undefined,
          name: "",
          provider_name: "",
          base_url: "",
          api_key: "",
          model_name: "",
          max_tokens: 512
        }
  );
  dialogVisible.value = true;
}

async function submitEmbedding() {
  await dialogFormRef.value?.validate();
  const payload: EmbeddingPayload = {
    name: dialogForm.name.trim(),
    provider_name: dialogForm.provider_name.trim(),
    base_url: dialogForm.base_url.trim(),
    model_name: dialogForm.model_name.trim(),
    max_tokens: dialogForm.max_tokens
  };
  if (dialogType.value === "add" || clearApiKey.value) {
    payload.api_key = clearApiKey.value
      ? null
      : dialogForm.api_key.trim() || null;
  } else if (dialogForm.api_key.trim()) {
    payload.api_key = dialogForm.api_key.trim();
  }

  dialogLoading.value = true;
  try {
    if (dialogType.value === "add") {
      await createEmbedding(payload);
      ElMessage.success(t("messages.addSuccess"));
    } else {
      await updateEmbedding(dialogForm.id!, payload);
      ElMessage.success(t("messages.editSuccess"));
    }
    dialogVisible.value = false;
    await Promise.all([fetchData(), loadOptions()]);
  } finally {
    dialogLoading.value = false;
  }
}

async function removeEmbedding(row: EmbeddingItem) {
  await deleteEmbedding(row.id);
  ElMessage.success(t("messages.deleteSuccess"));
  if (tableData.value.length === 1 && pagination.currentPage > 1) {
    pagination.currentPage--;
  }
  await Promise.all([fetchData(), loadOptions()]);
}

onMounted(() => Promise.all([fetchData(), loadOptions()]));
useQuickAction("create", () => openDialog("add"));
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

@media (width <= 680px) {
  :deep(.el-dialog) {
    width: 94% !important;
  }
}
</style>
