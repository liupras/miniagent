<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('domain.name')" prop="keyword">
        <el-input
          v-model="searchForm.keyword"
          :placeholder="t('domain.namePlaceholder')"
          clearable
          class="w-45!"
          @keyup.enter="onSearch"
        />
      </el-form-item>

      <el-form-item :label="t('domain.type')" prop="type">
        <el-select
          v-model="searchForm.type"
          :placeholder="t('domain.typePlaceholder')"
          clearable
          class="w-45!"
        >
          <el-option
            v-for="opt in DOMAIN_TYPE_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button
          v-auth="'domain:list'"
          type="primary"
          :icon="Search"
          @click="onSearch"
        >
          {{ t("buttons.search") }}
        </el-button>
        <el-button v-auth="'domain:list'" :icon="Refresh" @click="onReset">
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('domain.tableTitle')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button
          v-auth="'domain:add'"
          type="primary"
          :icon="Plus"
          @click="openDialog('add')"
        >
          {{ t("buttons.add") }}
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
          @page-size-change="handleSizeChange"
          @page-current-change="handleCurrentChange"
        >
          <template #operation="{ row }">
            <el-button
              v-auth="'domain:edit'"
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
                <el-button
                  v-auth="'domain:delete'"
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

    <el-dialog
      v-model="dialogVisible"
      :title="dialogType === 'add' ? t('domain.new') : t('domain.edit')"
      width="680px"
      destroy-on-close
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="dialogRules"
        label-width="140px"
      >
        <el-form-item :label="t('domain.name')" prop="name">
          <el-input
            v-model="dialogForm.name"
            :disabled="dialogType === 'edit'"
          />
        </el-form-item>

        <el-form-item :label="t('domain.type')" prop="type">
          <el-input v-model="dialogForm.type" />
        </el-form-item>

        <el-form-item
          :label="t('domain.processorClass')"
          prop="processor_class"
        >
          <el-input v-model="dialogForm.processor_class" />
        </el-form-item>

        <el-form-item :label="t('domain.pluginClass')" prop="plugin_class">
          <el-input v-model="dialogForm.plugin_class" />
        </el-form-item>

        <el-form-item :label="t('domain.description')" prop="description">
          <el-input
            v-model="dialogForm.description"
            type="textarea"
            :rows="2"
          />
        </el-form-item>

        <el-form-item
          :label="t('domain.metadataSchema')"
          prop="metadata_schema"
        >
          <div class="w-full">
            <el-input
              v-model="dialogForm.metadata_schema"
              type="textarea"
              :rows="5"
              class="font-mono text-xs"
              @blur="validateJsonField('metadata_schema')"
            />
            <div
              v-if="jsonError.metadata_schema"
              class="text-red-400 text-xs mt-1"
            >
              {{ jsonError.metadata_schema }}
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
import { ElMessage, type FormRules } from "element-plus";
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";

import {
  getDomainList,
  createDomain,
  updateDomain,
  deleteDomain
} from "@/api/domain";

const { t } = useI18n();
import { PureTableBar } from "@/components/RePureTableBar";
import { hasAuth } from "@/router/utils";

// ── Constants ──
const DOMAIN_TYPE_OPTIONS = [
  { label: "General", value: "general" },
  { label: "Law", value: "law" },
  { label: "Doctor", value: "doctor" }
];

// ── State ──
const loading = ref(false);
const tableData = ref([]);
const searchForm = reactive({ keyword: "", type: "" });
const pagination = reactive({ total: 0, pageSize: 20, currentPage: 1 });

const dialogVisible = ref(false);
const dialogLoading = ref(false);
const dialogType = ref<"add" | "edit">("add");
const jsonError = reactive({ metadata_schema: "" });
const dialogForm = reactive({
  id: undefined,
  name: "",
  type: "",
  processor_class: "",
  plugin_class: "",
  description: "",
  metadata_schema: "{}"
});

// ── Validation ──
const validateJsonField = (field: "metadata_schema") => {
  const val = dialogForm[field].trim();
  try {
    JSON.parse(val || "{}");
    jsonError[field] = "";
    return true;
  } catch {
    jsonError[field] = t("common.jsonFormatError");
    return false;
  }
};

const dialogRules: FormRules = {
  name: [
    { required: true, message: t("domain.nameRequired"), trigger: "blur" },
    { pattern: /^[^\s]+$/, message: t("domain.nameNoSpace"), trigger: "blur" }
  ],
  type: [
    { required: true, message: t("domain.typeRequired"), trigger: "blur" }
  ],
  processor_class: [
    { required: true, message: t("domain.classRequired"), trigger: "blur" }
  ],
  plugin_class: [
    { required: true, message: t("domain.classRequired"), trigger: "blur" }
  ]
};

// ── Table Columns ──
const columns: TableColumnList = [
  { label: "ID", prop: "id", width: 70 },
  { label: t("domain.name"), prop: "name", minWidth: 120 },
  { label: t("domain.type"), prop: "type", width: 100 },
  {
    label: t("domain.processorClass"),
    prop: "processor_class",
    minWidth: 150,
    showOverflowTooltip: true
  },
  {
    label: t("domain.pluginClass"),
    prop: "plugin_class",
    minWidth: 150,
    showOverflowTooltip: true
  },
  {
    label: t("common.updatedAt"),
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
    label: t("common.operation"),
    prop: "operation",
    width: 150,
    fixed: "right",
    slot: "operation",
    hide: !hasAuth("domain:edit") && !hasAuth("domain:delete")
  }
];

// ── API Methods ──
async function fetchData() {
  loading.value = true;
  const res: any = await getDomainList({
    page: pagination.currentPage,
    page_size: pagination.pageSize,
    ...searchForm
  });
  tableData.value = res.items;
  pagination.total = res.total;
  loading.value = false;
}

function onSearch() {
  fetchData();
}
function onReset() {
  searchForm.keyword = "";
  searchForm.type = "";
  fetchData();
}

function openDialog(type: "add" | "edit", row?: any) {
  dialogType.value = type;
  if (type === "edit" && row) {
    Object.assign(dialogForm, {
      ...row,
      metadata_schema: JSON.stringify(row.metadata_schema || {}, null, 2)
    });
  } else {
    Object.assign(dialogForm, {
      id: undefined,
      name: "",
      type: "",
      processor_class: "",
      plugin_class: "",
      description: "",
      metadata_schema: "{}"
    });
  }
  dialogVisible.value = true;
}

async function onSubmit() {
  if (!validateJsonField("metadata_schema")) return;
  const payload = {
    ...dialogForm,
    metadata_schema: JSON.parse(dialogForm.metadata_schema)
  };
  dialogLoading.value = true;
  if (dialogType.value === "add") await createDomain(payload);
  else await updateDomain(dialogForm.id!, payload);
  ElMessage.success(t("common.addSuccess"));
  dialogVisible.value = false;
  fetchData();
  dialogLoading.value = false;
}

async function onDelete(row: any) {
  await deleteDomain(row.id);
  ElMessage.success(t("common.deleteSuccess"));
  fetchData();
}

function handleSizeChange(val: number) {
  pagination.pageSize = val;
  fetchData();
}

function handleCurrentChange(val: number) {
  pagination.currentPage = val;
  fetchData();
}

onMounted(() => fetchData());
</script>
