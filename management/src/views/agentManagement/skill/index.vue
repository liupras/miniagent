<template>
  <div class="main">
    <!-- ── Search Bar ── -->
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('form.name.label')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          :placeholder="t('search.name.placeholder')"
          clearable
          class="w-45!"
          @keyup.enter="onSearch"
        />
      </el-form-item>

      <el-form-item :label="t('form.type.label')" prop="tool_type">
        <el-select
          v-model="searchForm.tool_type"
          :placeholder="t('search.type.placeholder')"
          clearable
          class="w-36!"
        >
          <el-option
            v-for="opt in TOOL_TYPE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item :label="t('labels.status')" prop="is_active">
        <el-select
          v-model="searchForm.is_active"
          :placeholder="t('search.status.placeholder')"
          clearable
          class="w-32.5!"
        >
          <el-option :label="t('buttons.active')" :value="true" />
          <el-option :label="t('buttons.inactive')" :value="false" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button
          v-auth="'tool:list'"
          type="primary"
          :icon="Search"
          @click="onSearch"
        >
          {{ t("buttons.search") }}
        </el-button>
        <el-button v-auth="'tool:list'" :icon="Refresh" @click="onReset">
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <!-- ── Toolbar + Table ── -->
    <PureTableBar
      :title="t('tool.tableTitle')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button
          v-auth="'tool:add'"
          type="primary"
          :icon="Plus"
          @click="openDialog('add')"
        >
          {{ t("buttons.add") }}
        </el-button>
        <el-button
          v-auth="'tool:delete'"
          type="danger"
          :icon="Delete"
          :disabled="!selectedIds.length"
          @click="onBatchDelete"
        >
          {{ t("buttons.batchDelete") }}
        </el-button>
      </template>

      <template #default="{ size, dynamicColumns }">
        <pure-table
          ref="tableRef"
          row-key="id"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :pagination="pagination"
          :paginationSmall="true"
          align-whole="center"
          @selection-change="handleSelectionChange"
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <!-- tool_type -->
          <template #tool_type="{ row }">
            <el-tag
              :type="getTagType(row.tool_type)"
              effect="plain"
              size="small"
            >
              {{ TYPE_LABEL_MAP[row.tool_type] ?? row.tool_type }}
            </el-tag>
          </template>

          <!-- is_active -->
          <template #is_active="{ row }">
            <el-switch
              v-model="row.is_active"
              v-auth="'tool:edit'"
              :active-text="t('buttons.active')"
              :inactive-text="t('buttons.inactive')"
              :loading="row._toggling"
              @change="onToggleActive(row)"
            />
          </template>

          <!-- description -->
          <template #description="{ row }">
            <el-tooltip
              :content="row.description"
              placement="top"
              :show-after="400"
              :disabled="!row.description"
            >
              <span
                class="truncate max-w-52 inline-block align-middle cursor-default"
              >
                {{ row.description || "—" }}
              </span>
            </el-tooltip>
          </template>

          <!-- operation -->
          <template #operation="{ row }">
            <el-button
              v-auth="'tool:edit'"
              type="primary"
              link
              size="small"
              :icon="EditPen"
              @click="openDialog('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-popconfirm
              :title="t('messages.deleteConfirm', { name: row.name })"
              @confirm="onDelete(row)"
            >
              <template #reference>
                <el-button
                  v-auth="'tool:delete'"
                  type="danger"
                  link
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

    <!-- ── Add / Edit Dialog ── -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? t('tool.new') : t('tool.edit')"
      width="680px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="110px"
      >
        <el-form-item :label="t('form.name.label')" prop="name">
          <el-input
            v-model="dialogForm.name"
            :placeholder="t('tool.name.placeholder')"
            :disabled="dialogType === 'edit'"
          />
        </el-form-item>

        <el-form-item :label="t('form.type.label')" prop="tool_type">
          <el-select
            v-model="dialogForm.tool_type"
            :placeholder="t('form.type.selectPlaceholder')"
            class="w-full"
          >
            <el-option
              v-for="opt in TOOL_TYPE_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item :label="t('form.description.label')" prop="description">
          <el-input
            v-model="dialogForm.description"
            type="textarea"
            :rows="2"
            :placeholder="t('form.description.placeholder')"
          />
        </el-form-item>

        <el-form-item :label="t('tool.toolSchema.label')" prop="tool_schema">
          <div class="w-full">
            <el-input
              v-model="dialogForm.tool_schema"
              type="textarea"
              :rows="9"
              :placeholder="t('tool.toolSchema.placeholder')"
              class="font-mono text-xs"
              @blur="validateJsonField('tool_schema')"
            />
            <div v-if="jsonError.tool_schema" class="text-red-400 text-xs mt-1">
              {{ jsonError.tool_schema }}
            </div>
          </div>
        </el-form-item>

        <el-form-item :label="t('tool.config.label')">
          <div class="w-full">
            <el-input
              v-model="dialogForm.config"
              type="textarea"
              :rows="5"
              :placeholder="t('tool.config.placeholder')"
              class="font-mono text-xs"
              @blur="validateJsonField('config')"
            />
            <div v-if="jsonError.config" class="text-red-400 text-xs mt-1">
              {{ jsonError.config }}
            </div>
          </div>
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
import { ref, reactive, onMounted } from "vue";
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
  getToolList,
  createTool,
  updateTool,
  deleteTool,
  bulkDeleteTools,
  toggleTool,
  type Tool,
  type ToolType,
  type ToolListParams
} from "@/api/tool";

const { t } = useI18n();

import { PureTableBar } from "@/components/RePureTableBar";
import { hasAuth } from "@/router/utils";

defineOptions({ name: "ToolManagement" });

// ── Constants ──────────────────────────────────────────────────────────────

const TOOL_TYPE_OPTIONS: { label: string; value: ToolType }[] = [
  { label: "Function", value: "function" },
  { label: "API", value: "api" },
  { label: "Smart Router", value: "smart_router" },
  { label: "SQL Agent", value: "sql_agent" }
];

const TYPE_LABEL_MAP: Record<string, string> = {
  function: "Function",
  api: "API",
  smart_router: "Smart Router",
  sql_agent: "SQL Agent"
};

// ── State ──────────────────────────────────────────────────────────────────

const loading = ref(false);
const tableData = ref<Tool[]>([]);
const selectedIds = ref<number[]>([]);
const searchFormRef = ref<FormInstance>();
const dialogFormRef = ref<FormInstance>();

const searchForm = reactive({
  keyword: "",
  tool_type: "" as ToolType | "",
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

// ── Dialog state ───────────────────────────────────────────────────────────

const dialogVisible = ref(false);
const dialogLoading = ref(false);
const dialogType = ref<"add" | "edit">("add");
const jsonError = reactive({ tool_schema: "", config: "" });

const dialogForm = reactive({
  id: undefined as number | undefined,
  name: "",
  description: "",
  tool_type: "function" as ToolType,
  tool_schema: "",
  config: "",
  is_active: true
});

const DEFAULT_SCHEMA = JSON.stringify(
  {
    type: "function",
    function: {
      name: "",
      description: "",
      parameters: { type: "object", properties: {}, required: [] }
    }
  },
  null,
  2
);

// ── Validation ─────────────────────────────────────────────────────────────

function validateJsonField(field: "tool_schema" | "config") {
  const val = dialogForm[field].trim();
  if (!val) {
    jsonError[field] = field === "tool_schema" ? t("validation.required") : "";
    return field !== "tool_schema";
  }
  try {
    JSON.parse(val);
    jsonError[field] = "";
    return true;
  } catch {
    jsonError[field] = t("messages.jsonFormatError");
    return false;
  }
}

const dialogRules: FormRules = {
  name: [
    { required: true, message: t("validation.required"), trigger: "blur" },
    {
      max: 100,
      message: t("validation.maxLength", { count: 100 }),
      trigger: "blur"
    },
    {
      pattern: /^[a-zA-Z][a-zA-Z0-9_]*$/,
      message: t("tool.name.pattern"),
      trigger: "blur"
    }
  ],
  tool_type: [
    { required: true, message: t("validation.required"), trigger: "change" }
  ],
  tool_schema: [
    { required: true, message: t("validation.required"), trigger: "blur" },
    {
      validator: (_rule, _val, callback) => {
        if (!validateJsonField("tool_schema"))
          callback(new Error(jsonError.tool_schema));
        else callback();
      },
      trigger: "blur"
    }
  ]
};

// ── Table columns ──────────────────────────────────────────────────────────

const columns: TableColumnList = [
  { type: "selection", width: 55, fixed: "left", reserveSelection: true },
  { label: "ID", prop: "id", width: 70 },
  { label: t("form.name.label"), prop: "name", minWidth: 160 },
  {
    label: t("form.type.label"),
    prop: "tool_type",
    width: 130,
    slot: "tool_type"
  },
  {
    label: t("form.description.label"),
    prop: "description",
    minWidth: 200,
    slot: "description"
  },
  {
    label: t("form.status"),
    prop: "is_active",
    width: 140,
    slot: "is_active",
    hide: !hasAuth("tool:edit")
  },
  {
    label: t("form.updatedAt"),
    prop: "updated_at",
    width: 170,
    formatter: ({ updated_at }) =>
      updated_at
        ? new Date(updated_at).toLocaleString("zh-CN", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false
          })
        : "—"
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 160,
    fixed: "right",
    slot: "operation",
    hide: !hasAuth("tool:edit") && !hasAuth("tool:delete")
  }
];

// ── Data fetching ──────────────────────────────────────────────────────────

async function fetchData() {
  loading.value = true;
  try {
    const params: ToolListParams = {
      page: pagination.currentPage,
      page_size: pagination.pageSize,
      keyword: searchForm.keyword || undefined,
      tool_type: searchForm.tool_type || undefined,
      is_active: searchForm.is_active
    };
    const res = await getToolList(params);
    tableData.value = res.data;
    pagination.total = res.total;
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
  searchForm.keyword = "";
  searchForm.tool_type = "";
  searchForm.is_active = undefined;
  onSearch();
}

function handleSelectionChange(rows: Tool[]) {
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

// ── Dialog ─────────────────────────────────────────────────────────────────

function openDialog(type: "add" | "edit", row?: Tool) {
  dialogType.value = type;
  jsonError.tool_schema = "";
  jsonError.config = "";

  if (type === "edit" && row) {
    Object.assign(dialogForm, {
      id: row.id,
      name: row.name,
      description: row.description ?? "",
      tool_type: row.tool_type,
      tool_schema: JSON.stringify(row.tool_schema, null, 2),
      config: row.config ? JSON.stringify(row.config, null, 2) : "",
      is_active: row.is_active
    });
  } else {
    Object.assign(dialogForm, {
      id: undefined,
      name: "",
      description: "",
      tool_type: "function",
      tool_schema: DEFAULT_SCHEMA,
      config: "",
      is_active: true
    });
  }
  dialogVisible.value = true;
}

async function onSubmit() {
  await dialogFormRef.value?.validate();
  if (!validateJsonField("tool_schema")) return;
  if (dialogForm.config.trim() && !validateJsonField("config")) return;

  dialogLoading.value = true;
  try {
    const payload = {
      name: dialogForm.name,
      description: dialogForm.description || null,
      tool_type: dialogForm.tool_type,
      tool_schema: JSON.parse(dialogForm.tool_schema),
      config: dialogForm.config.trim() ? JSON.parse(dialogForm.config) : null,
      is_active: dialogForm.is_active
    };

    if (dialogType.value === "add") {
      await createTool(payload);
      ElMessage.success(t("messages.addSuccess"));
    } else {
      await updateTool(dialogForm.id!, payload);
      ElMessage.success(t("messages.editSuccess"));
    }

    dialogVisible.value = false;
    fetchData();
  } finally {
    dialogLoading.value = false;
  }
}

// ── CRUD actions ───────────────────────────────────────────────────────────

async function onDelete(row: Tool) {
  await deleteTool(row.id);
  ElMessage.success(t("messages.deleteSuccess"));
  fetchData();
}

async function onBatchDelete() {
  await ElMessageBox.confirm(
    t("messages.batchDeleteConfirm", { count: selectedIds.value.length }),
    t("messages.warning"),
    { type: "warning" }
  );
  await bulkDeleteTools(selectedIds.value);
  ElMessage.success(t("messages.deleteSuccess"));

  fetchData();
}

async function onToggleActive(row: any) {
  row._toggling = true;
  try {
    await toggleTool(row.id);
    ElMessage.success(
      row.is_active ? t("labels.activated") : t("labels.deactivated")
    );
  } catch {
    row.is_active = !row.is_active; // revert on error
  } finally {
    row._toggling = false;
  }
}

function getTagType(type: ToolType) {
  switch (type) {
    case "api":
      return "success";

    case "smart_router":
      return "info";

    case "sql_agent":
      return "warning";

    default:
      return undefined;
  }
}

// ── Init ───────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}
</style>
