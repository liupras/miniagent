<template>
  <div class="main">
    <!-- ── Table bar ─────────────────────────────────────────────── -->
    <PureTableBar
      :title="$t('routerConfig.title')"
      :columns="columns"
      @refresh="fetchList"
    >
      <template v-slot="{ size, dynamicColumns }">
        <pure-table
          row-key="config_id"
          :loading="loading"
          :size="size"
          :data="tableData"
          :columns="dynamicColumns"
          :pagination="pagination"
          :paginationSmall="size === 'small'"
          adaptive
        >
          <!-- ── Actions slot ──────────────────────────────────────── -->
          <template #operation="{ row }">
            <el-button
              v-auth="'router_config:edit'"
              link
              type="primary"
              :icon="useRenderIcon(EditPen)"
              @click="openEdit(row)"
            >
              {{ $t("buttons.edit") }}
            </el-button>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <!-- ── Edit dialog ───────────────────────────────────────────── -->
    <el-dialog
      v-model="dialogVisible"
      :title="$t('routerConfig.editTitle')"
      width="520px"
      draggable
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="130px"
        label-position="right"
      >
        <!-- Config ID – read-only display -->
        <el-form-item :label="$t('routerConfig.configId')">
          <el-input :value="editingId" disabled />
        </el-form-item>

        <!-- Selection strategy -->
        <el-form-item
          :label="$t('routerConfig.selectionStrategy')"
          prop="selection_strategy"
        >
          <el-select
            v-model="form.selection_strategy"
            :placeholder="$t('routerConfig.selectionStrategyPlaceholder')"
            style="width: 100%"
          >
            <el-option
              value="keyword"
              :label="$t('routerConfig.strategy.keyword')"
            />
            <el-option
              value="embedding"
              :label="$t('routerConfig.strategy.embedding')"
            />
          </el-select>
        </el-form-item>

        <!-- Fallback to all -->
        <el-form-item
          :label="$t('routerConfig.fallbackToAll')"
          prop="fallback_to_all"
        >
          <el-switch v-model="form.fallback_to_all" />
        </el-form-item>

        <!-- Max KB count -->
        <el-form-item
          :label="$t('routerConfig.maxKbCount')"
          prop="max_kb_count"
        >
          <el-input-number
            v-model="form.max_kb_count"
            :min="1"
            :precision="0"
            controls-position="right"
            style="width: 100%"
            :placeholder="$t('routerConfig.maxKbCountPlaceholder')"
          />
        </el-form-item>

        <!-- Extra config (JSON textarea) -->
        <el-form-item :label="$t('routerConfig.extraConfig')">
          <div style="width: 100%">
            <el-input
              v-model="form.extra_config_str"
              type="textarea"
              :rows="6"
              :placeholder="$t('routerConfig.extraConfigPlaceholder')"
              :status="extraConfigInvalid ? 'error' : ''"
              style="font-family: monospace; font-size: 12px"
              @input="handleExtraConfigInput"
            />
            <div
              style="
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-top: 4px;
              "
            >
              <span
                v-if="extraConfigInvalid"
                style="font-size: 12px; color: var(--el-color-danger)"
              >
                {{ $t("routerConfig.extraConfigInvalid") }}
              </span>
              <span v-else />
              <el-button link type="primary" size="small" @click="formatJson">
                {{ $t("routerConfig.extraConfigFormatBtn") }}
              </el-button>
            </div>
          </div>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="handleCancel">
          {{ $t("buttons.cancel") }}
        </el-button>
        <el-button
          v-auth="'router_config:edit'"
          type="primary"
          :loading="saveLoading"
          @click="handleSave"
        >
          {{ $t("buttons.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, h } from "vue";
import { useI18n } from "vue-i18n";
import {
  ElMessage,
  ElTag,
  type FormInstance,
  type FormRules
} from "element-plus";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { PureTableBar } from "@/components/RePureTableBar";
import type { PaginationProps } from "@pureadmin/table";

import {
  getRouterConfigList,
  updateRouterConfig,
  type RouterConfigItem,
  type RouterConfigUpdatePayload
} from "@/api/router_config";

import EditPen from "~icons/ep/edit-pen";
import { hasAuth } from "@/router/utils";

// ─── i18n ─────────────────────────────────────────────────────────────────────

const { t } = useI18n();

// ─── Table state ──────────────────────────────────────────────────────────────

const loading = ref(false);
const tableData = ref<RouterConfigItem[]>([]);

const pagination = reactive<PaginationProps>({
  total: 0,
  pageSize: 10,
  currentPage: 1,
  background: true
});

// ─── Table columns ────────────────────────────────────────────────────────────

const STRATEGY_TAG_TYPE: Record<string, "primary" | "success"> = {
  keyword: "primary",
  embedding: "success"
};

const columns: TableColumnList = [
  {
    label: t("routerConfig.configId"),
    prop: "config_id",
    minWidth: 220,
    showOverflowTooltip: true
  },
  {
    label: t("routerConfig.selectionStrategy"),
    prop: "selection_strategy",
    minWidth: 130,
    cellRenderer: ({ row }) =>
      h(
        ElTag,
        {
          type: STRATEGY_TAG_TYPE[row.selection_strategy] ?? "info",
          size: "small"
        },
        { default: () => t(`routerConfig.strategy.${row.selection_strategy}`) }
      )
  },
  {
    label: t("routerConfig.fallbackToAll"),
    prop: "fallback_to_all",
    minWidth: 120,
    cellRenderer: ({ row }) =>
      h(
        ElTag,
        { type: row.fallback_to_all ? "success" : "info", size: "small" },
        {
          default: () =>
            row.fallback_to_all ? t("common.yes") : t("common.no")
        }
      )
  },
  {
    label: t("routerConfig.maxKbCount"),
    prop: "max_kb_count",
    minWidth: 110,
    align: "center"
  },
  {
    label: t("common.createdAt"),
    prop: "created_at",
    minWidth: 180,
    formatter: ({ created_at }) =>
      created_at ? new Date(created_at).toLocaleString() : "-"
  },
  {
    label: t("common.actions"),
    fixed: "right",
    width: 90,
    slot: "operation",
    hide: !hasAuth("router_config:edit")
  }
];

// ─── Fetch data ───────────────────────────────────────────────────────────────

async function fetchList() {
  loading.value = true;
  try {
    const res = await getRouterConfigList();
    tableData.value = res ?? [];
    pagination.total = tableData.value.length;
  } finally {
    loading.value = false;
  }
}

fetchList();

// ─── Edit dialog ──────────────────────────────────────────────────────────────

const dialogVisible = ref(false);
const saveLoading = ref(false);
const editingId = ref("");
const formRef = ref<FormInstance>();

const form = reactive<{
  selection_strategy: "keyword" | "embedding";
  fallback_to_all: boolean;
  max_kb_count: number;
  extra_config_str: string;
}>({
  selection_strategy: "embedding",
  fallback_to_all: true,
  max_kb_count: 3,
  extra_config_str: ""
});

// JSON inline validation flag
const extraConfigInvalid = ref(false);

function validateExtraConfig(str: string): boolean {
  if (!str.trim()) return true; // empty is fine (null)
  try {
    JSON.parse(str);
    return true;
  } catch {
    return false;
  }
}

const formRules = computed<FormRules>(() => ({
  selection_strategy: [
    { required: true, message: t("routerConfig.required"), trigger: "change" }
  ],
  max_kb_count: [
    { required: true, message: t("routerConfig.required"), trigger: "blur" },
    {
      type: "number",
      min: 1,
      message: t("routerConfig.maxKbCountMin"),
      trigger: "blur"
    }
  ]
}));

function openEdit(row: RouterConfigItem) {
  editingId.value = row.config_id;
  form.selection_strategy = row.selection_strategy;
  form.fallback_to_all = row.fallback_to_all;
  form.max_kb_count = row.max_kb_count;
  form.extra_config_str = row.extra_config
    ? JSON.stringify(row.extra_config, null, 2)
    : "";
  extraConfigInvalid.value = false;
  dialogVisible.value = true;
}

function formatJson() {
  const str = form.extra_config_str.trim();
  if (!str) return;
  try {
    form.extra_config_str = JSON.stringify(JSON.parse(str), null, 2);
    extraConfigInvalid.value = false;
  } catch {
    extraConfigInvalid.value = true;
  }
}

function handleExtraConfigInput() {
  extraConfigInvalid.value = !validateExtraConfig(form.extra_config_str);
}

async function handleSave() {
  if (!formRef.value) return;
  await formRef.value.validate(async valid => {
    if (!valid) return;

    // Final JSON check before submit
    if (!validateExtraConfig(form.extra_config_str)) {
      extraConfigInvalid.value = true;
      return;
    }

    const payload: RouterConfigUpdatePayload = {
      selection_strategy: form.selection_strategy,
      fallback_to_all: form.fallback_to_all,
      max_kb_count: form.max_kb_count,
      extra_config: form.extra_config_str.trim()
        ? JSON.parse(form.extra_config_str)
        : null
    };

    saveLoading.value = true;
    try {
      await updateRouterConfig(editingId.value, payload);
      ElMessage.success(t("common.saveSuccess"));
      dialogVisible.value = false;
      await fetchList();
    } catch {
      ElMessage.error(t("common.saveFailed"));
    } finally {
      saveLoading.value = false;
    }
  });
}

function handleCancel() {
  dialogVisible.value = false;
  formRef.value?.resetFields();
}
</script>
