<template>
  <div class="main">
    <!-- ── Search Bar ── -->
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('agentManagement.name')" prop="name">
        <el-input
          v-model="searchForm.name"
          :placeholder="t('agentManagement.namePlaceholder')"
          clearable
          class="w-45!"
          @keyup.enter="onSearch"
        />
      </el-form-item>

      <el-form-item :label="t('agentManagement.llm')" prop="llm_id">
        <el-select
          v-model="searchForm.llm_id"
          :placeholder="t('agentManagement.llmPlaceholder')"
          clearable
          class="w-40!"
        >
          <el-option
            v-for="llm in llmOptions"
            :key="llm.id"
            :label="llm.name"
            :value="llm.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('agentManagement.user')" prop="user_id">
        <el-select
          v-model="searchForm.user_id"
          :placeholder="t('agentManagement.userPlaceholder')"
          clearable
          filterable
          class="w-40!"
        >
          <el-option
            v-for="user in userOptions"
            :key="user.id"
            :label="user.username"
            :value="user.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('common.status')" prop="is_active">
        <el-select
          v-model="searchForm.is_active"
          :placeholder="t('common.statusPlaceholder')"
          clearable
          class="w-32.5!"
        >
          <el-option :label="t('buttons.active')" :value="true" />
          <el-option :label="t('buttons.inactive')" :value="false" />
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

    <!-- ── Toolbar ── -->
    <PureTableBar
      :title="t('agentManagement.tableTitle')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button type="primary" :icon="Plus" @click="openDialog('add')">
          {{ t("buttons.add") }}
        </el-button>
        <el-button
          type="danger"
          :icon="Delete"
          :disabled="!selectedIds.length"
          @click="onBatchDelete"
        >
          {{ t("buttons.batchDelete") }}
        </el-button>
      </template>
    </PureTableBar>

    <!-- ── Table ── -->
    <pure-table
      ref="tableRef"
      row-key="id"
      :data="tableData"
      :columns="columns"
      :loading="loading"
      :pagination="pagination"
      :paginationSmall="true"
      align-whole="center"
      @selection-change="handleSelectionChange"
      @page-size-change="handleSizeChange"
      @page-current-change="handleCurrentChange"
    >
      <!-- Status column -->
      <template #is_active="{ row }">
        <el-switch
          v-model="row.is_active"
          :active-text="t('buttons.active')"
          :inactive-text="t('buttons.inactive')"
          :loading="row._toggling"
          @change="onToggleActive(row)"
        />
      </template>

      <!-- LLM column -->
      <template #llm="{ row }">
        <el-tag v-if="row.llm" type="info" effect="plain">
          {{ row.llm.name }}
        </el-tag>
        <span v-else class="text-gray-400">—</span>
      </template>

      <!-- Users column -->
      <template #users="{ row }">
        <template v-if="row.users && row.users.length">
          <el-tag
            v-for="u in row.users.slice(0, 2)"
            :key="u.id"
            class="mr-1"
            size="small"
          >
            {{ u.username }}
          </el-tag>
          <el-tag v-if="row.users.length > 2" size="small" type="info">
            +{{ row.users.length - 2 }}
          </el-tag>
        </template>
        <span v-else class="text-gray-400">—</span>
      </template>

      <!-- System prompt – truncated -->
      <template #system_prompt="{ row }">
        <el-tooltip
          :content="row.system_prompt"
          placement="top"
          :show-after="400"
        >
          <span
            class="truncate max-w-45 inline-block align-middle cursor-default"
          >
            {{ row.system_prompt }}
          </span>
        </el-tooltip>
      </template>

      <!-- Actions column -->
      <template #operation="{ row }">
        <el-button
          type="primary"
          link
          size="small"
          :icon="EditPen"
          @click="openDialog('edit', row)"
        >
          {{ t("buttons.edit") }}
        </el-button>
        <el-popconfirm
          :title="t('common.deleteConfirm', { name: row.name })"
          @confirm="onDelete(row)"
        >
          <template #reference>
            <el-button type="danger" link size="small" :icon="Delete">
              {{ t("buttons.delete") }}
            </el-button>
          </template>
        </el-popconfirm>
      </template>
    </pure-table>

    <!-- ── Dialog: Add / Edit ── -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? t('buttons.add') : t('buttons.edit')"
      width="600px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="110px"
      >
        <el-form-item :label="t('agentManagement.name')" prop="name">
          <el-input
            v-model="dialogForm.name"
            :placeholder="t('agentManagement.namePlaceholder')"
          />
        </el-form-item>

        <el-form-item
          :label="t('agentManagement.description')"
          prop="description"
        >
          <el-input
            v-model="dialogForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('agentManagement.descriptionPlaceholder')"
          />
        </el-form-item>

        <el-form-item
          :label="t('agentManagement.systemPrompt')"
          prop="system_prompt"
        >
          <el-input
            v-model="dialogForm.system_prompt"
            type="textarea"
            :rows="5"
            :placeholder="t('agentManagement.systemPromptPlaceholder')"
          />
        </el-form-item>

        <el-form-item :label="t('agentManagement.llm')" prop="llm_id">
          <el-select
            v-model="dialogForm.llm_id"
            clearable
            :placeholder="t('agentManagement.llmPlaceholder')"
            class="w-full"
          >
            <el-option
              v-for="llm in llmOptions"
              :key="llm.id"
              :label="llm.name"
              :value="llm.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('common.status')" prop="is_active">
          <el-switch
            v-model="dialogForm.is_active"
            :active-text="t('buttons.active')"
            :inactive-text="t('buttons.inactive')"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="onSubmit">
          {{ t("buttons.confirm") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from "vue";
import { useI18n } from "vue-i18n";
import {
  ElMessage,
  ElMessageBox,
  type FormInstance,
  type FormRules
} from "element-plus";

import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";

import {
  getAgentList,
  createAgent,
  updateAgent,
  deleteAgent,
  batchDeleteAgents,
  toggleAgentActive,
  getLLMOptions,
  getUserOptions
} from "@/api/agent";

defineOptions({ name: "AgentManagement" });

const { t } = useI18n();

// ── State ──────────────────────────────────────────────────────────────────
const loading = ref(false);
const tableData = ref<any[]>([]);
const selectedIds = ref<number[]>([]);
const tableRef = ref();
const searchFormRef = ref<FormInstance>();
const dialogFormRef = ref<FormInstance>();

const llmOptions = ref<{ id: number; name: string }[]>([]);
const userOptions = ref<{ id: number; username: string }[]>([]);

const searchForm = reactive({
  name: "",
  llm_id: undefined as number | undefined,
  user_id: undefined as number | undefined,
  is_active: undefined as boolean | undefined
});

const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true,
  layout: "total, sizes, prev, pager, next, jumper",
  pageSizes: [10, 20, 50, 100]
});

// ── Dialog ─────────────────────────────────────────────────────────────────
const dialogVisible = ref(false);
const dialogLoading = ref(false);
const dialogType = ref<"add" | "edit">("add");
const dialogForm = reactive({
  id: undefined as number | undefined,
  name: "",
  description: "",
  system_prompt: "",
  llm_id: undefined as number | undefined,
  is_active: true
});

const dialogRules: FormRules = {
  name: [
    {
      required: true,
      message: () => t("agentManagement.nameRequired"),
      trigger: "blur"
    },
    {
      max: 100,
      message: () => t("agentManagement.nameMaxLength"),
      trigger: "blur"
    }
  ],
  system_prompt: [
    {
      required: true,
      message: () => t("agentManagement.systemPromptRequired"),
      trigger: "blur"
    }
  ]
};

// ── Table column definitions ───────────────────────────────────────────────
const columns: TableColumnList = [
  { type: "selection", width: 55, fixed: "left", reserveSelection: true },
  { label: "ID", prop: "id", width: 70 },
  { label: t("agentManagement.name"), prop: "name", minWidth: 140 },
  {
    label: t("agentManagement.description"),
    prop: "description",
    minWidth: 160,
    showOverflowTooltip: true
  },
  {
    label: t("agentManagement.systemPrompt"),
    prop: "system_prompt",
    minWidth: 200,
    slot: "system_prompt"
  },
  {
    label: t("agentManagement.llm"),
    prop: "llm",
    width: 140,
    slot: "llm"
  },
  {
    label: t("agentManagement.boundUsers"),
    prop: "users",
    minWidth: 160,
    slot: "users"
  },
  {
    label: t("common.status"),
    prop: "is_active",
    width: 140,
    slot: "is_active"
  },
  {
    label: t("common.createdAt"),
    prop: "created_at",
    width: 170,
    formatter: ({ created_at }) =>
      created_at ? new Date(created_at).toLocaleString() : "—"
  },
  {
    label: t("common.operation"),
    prop: "operation",
    width: 140,
    fixed: "right",
    slot: "operation"
  }
];

// ── Methods ────────────────────────────────────────────────────────────────
async function fetchData() {
  loading.value = true;
  try {
    const params = {
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      name: searchForm.name || undefined,
      llm_id: searchForm.llm_id,
      user_id: searchForm.user_id,
      is_active: searchForm.is_active
    };
    const res = await getAgentList(params);
    tableData.value = res.data.data;
    pagination.total = res.data.total;
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
  searchForm.name = "";
  searchForm.llm_id = undefined;
  searchForm.user_id = undefined;
  searchForm.is_active = undefined;
  onSearch();
}

function handleSelectionChange(rows: any[]) {
  selectedIds.value = rows.map(r => r.id);
}

function handleSizeChange(val: number) {
  pagination.pageSize = val;
  fetchData();
}

function handleCurrentChange(val: number) {
  pagination.currentPage = val;
  fetchData();
}

function openDialog(type: "add" | "edit", row?: any) {
  dialogType.value = type;
  if (type === "edit" && row) {
    Object.assign(dialogForm, {
      id: row.id,
      name: row.name,
      description: row.description ?? "",
      system_prompt: row.system_prompt,
      llm_id: row.llm?.id ?? undefined,
      is_active: row.is_active
    });
  } else {
    Object.assign(dialogForm, {
      id: undefined,
      name: "",
      description: "",
      system_prompt: "",
      llm_id: undefined,
      is_active: true
    });
  }
  dialogVisible.value = true;
}

async function onSubmit() {
  await dialogFormRef.value?.validate();
  dialogLoading.value = true;
  try {
    const payload = {
      name: dialogForm.name,
      description: dialogForm.description || null,
      system_prompt: dialogForm.system_prompt,
      llm_id: dialogForm.llm_id ?? null,
      is_active: dialogForm.is_active
    };

    if (dialogType.value === "add") {
      await createAgent(payload);
      ElMessage.success(t("common.addSuccess"));
    } else {
      await updateAgent(dialogForm.id!, payload);
      ElMessage.success(t("common.editSuccess"));
    }

    dialogVisible.value = false;
    fetchData();
  } finally {
    dialogLoading.value = false;
  }
}

async function onDelete(row: any) {
  await deleteAgent(row.id);
  ElMessage.success(t("common.deleteSuccess"));
  fetchData();
}

async function onBatchDelete() {
  await ElMessageBox.confirm(
    t("common.batchDeleteConfirm", { count: selectedIds.value.length }),
    t("common.warning"),
    { type: "warning" }
  );
  await batchDeleteAgents(selectedIds.value);
  ElMessage.success(t("common.deleteSuccess"));
  tableRef.value?.clearSelection();
  fetchData();
}

async function onToggleActive(row: any) {
  row._toggling = true;
  try {
    await toggleAgentActive(row.id);
    ElMessage.success(
      row.is_active ? t("common.activated") : t("common.deactivated")
    );
  } catch {
    row.is_active = !row.is_active; // revert on error
  } finally {
    row._toggling = false;
  }
}

// ── Init ───────────────────────────────────────────────────────────────────
onMounted(async () => {
  fetchData();
  const [llmRes, userRes] = await Promise.all([
    getLLMOptions(),
    getUserOptions()
  ]);
  llmOptions.value = llmRes.data;
  userOptions.value = userRes.data;
});
</script>

<style scoped>
:deep(.el-dropdown-menu__item i) {
  margin: 0;
}
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
</style>
