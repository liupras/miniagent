<template>
  <div class="main">
    <el-form
      :inline="true"
      class="search-form bg-bg_color w-[99/100] overflow-auto pl-8 pt-3"
    >
      <el-form-item :label="t('systemSetting.group')">
        <el-select
          v-model="selectedGroup"
          clearable
          class="w-48!"
          :placeholder="t('systemSetting.allGroups')"
          @change="fetchSettings"
        >
          <el-option
            v-for="group in groupOptions"
            :key="group"
            :label="group"
            :value="group"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('systemSetting.title')"
      :columns="columns"
      @refresh="fetchSettings"
    >
      <template #default="{ size, dynamicColumns }">
        <pure-table
          row-key="key"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          adaptive
          align-whole="center"
        >
          <template #key="{ row }">
            <code class="text-sm">{{ row.key }}</code>
          </template>
          <template #value="{ row }">
            <span class="setting-value">{{ formatValue(row) }}</span>
          </template>
          <template #valueType="{ row }">
            <el-tag effect="plain" :type="typeTag(row.value_type)">
              {{ row.value_type }}
            </el-tag>
          </template>
          <template #readonly="{ row }">
            <el-tag :type="row.is_readonly ? 'info' : 'success'">
              {{
                row.is_readonly
                  ? t("systemSetting.readonly")
                  : t("systemSetting.editable")
              }}
            </el-tag>
          </template>
          <template #operation="{ row }">
            <el-button
              v-if="!row.is_readonly && hasPerms('system_setting:edit')"
              link
              type="primary"
              :icon="EditPen"
              @click="openEditor(row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <span v-else class="text-gray-400">-</span>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <el-dialog
      v-model="dialogVisible"
      :title="t('systemSetting.editTitle')"
      width="600px"
      destroy-on-close
      :close-on-click-modal="false"
    >
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-width="110px"
      >
        <el-form-item :label="t('systemSetting.key')">
          <el-input :model-value="editingSetting?.key" disabled />
        </el-form-item>
        <el-form-item :label="t('systemSetting.type')">
          <el-input :model-value="editingSetting?.value_type" disabled />
        </el-form-item>
        <el-form-item :label="t('systemSetting.description')">
          <span class="description-text">
            {{ editingSetting?.description || "-" }}
          </span>
        </el-form-item>
        <el-form-item :label="t('systemSetting.value')" prop="value">
          <el-select
            v-if="editingSetting?.key === 'system_language'"
            v-model="form.value"
            class="w-full"
            :placeholder="t('systemSetting.valuePlaceholder')"
          >
            <el-option
              v-for="language in languageOptions"
              :key="language.value"
              :label="language.label"
              :value="language.value"
            />
          </el-select>
          <el-switch
            v-else-if="editingSetting?.value_type === 'bool'"
            v-model="form.boolValue"
          />
          <el-input
            v-else
            v-model="form.value"
            :type="editingSetting?.value_type === 'json' ? 'textarea' : 'text'"
            :rows="editingSetting?.value_type === 'json' ? 10 : undefined"
            :class="{ 'json-editor': editingSetting?.value_type === 'json' }"
            :placeholder="t('systemSetting.valuePlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">
          {{ t("buttons.cancel") }}
        </el-button>
        <el-button type="primary" :loading="saving" @click="saveSetting">
          {{ t("buttons.save") }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import dayjs from "dayjs";
import EditPen from "~icons/ep/edit-pen";
import { PureTableBar } from "@/components/RePureTableBar";
import { hasPerms } from "@/utils/auth";
import {
  getSystemSettings,
  updateSystemSetting,
  type SystemSettingItem,
  type SystemSettingValueType
} from "@/api/system_setting";

defineOptions({ name: "SystemSettingManagement" });

const { t } = useI18n();
const loading = ref(false);
const saving = ref(false);
const tableData = ref<SystemSettingItem[]>([]);
const allGroups = ref<string[]>([]);
const selectedGroup = ref("");
const groupOptions = computed(() => allGroups.value);
const languageOptions = [
  { label: "简体中文 (zh_CN)", value: "zh_CN" },
  { label: "English (en_US)", value: "en_US" }
];

const columns: TableColumnList = [
  { label: t("systemSetting.key"), prop: "key", minWidth: 190, slot: "key" },
  {
    label: t("systemSetting.value"),
    prop: "value",
    minWidth: 180,
    slot: "value"
  },
  {
    label: t("systemSetting.type"),
    prop: "value_type",
    width: 100,
    slot: "valueType"
  },
  { label: t("systemSetting.group"), prop: "group", width: 120 },
  {
    label: t("systemSetting.description"),
    prop: "description",
    minWidth: 260,
    showOverflowTooltip: true
  },
  {
    label: t("systemSetting.access"),
    prop: "is_readonly",
    width: 110,
    slot: "readonly"
  },
  {
    label: t("form.updatedAt"),
    prop: "updated_at",
    width: 165,
    formatter: ({ updated_at }) =>
      updated_at ? dayjs(updated_at).format("YYYY-MM-DD HH:mm") : "-"
  },
  {
    label: t("labels.operation"),
    prop: "operation",
    width: 90,
    fixed: "right",
    slot: "operation"
  }
];

function typeTag(type: SystemSettingValueType) {
  const tags = {
    string: "primary",
    int: "success",
    float: "success",
    bool: "warning",
    json: "danger"
  } as const;
  return tags[type];
}

function formatValue(setting: SystemSettingItem) {
  if (setting.value_type !== "json") return setting.value;
  try {
    return JSON.stringify(JSON.parse(setting.value));
  } catch {
    return setting.value;
  }
}

async function fetchSettings() {
  loading.value = true;
  try {
    const settings = await getSystemSettings(selectedGroup.value || undefined);
    tableData.value = settings ?? [];
    if (!selectedGroup.value) {
      allGroups.value = [...new Set(tableData.value.map(item => item.group))];
    }
  } finally {
    loading.value = false;
  }
}

const dialogVisible = ref(false);
const editingSetting = ref<SystemSettingItem>();
const formRef = ref<FormInstance>();
const form = reactive({ value: "", boolValue: false });

const formRules = computed<FormRules>(() => ({
  value: [
    {
      validator: (_rule, value: string, callback) => {
        const type = editingSetting.value?.value_type;
        const normalized = value.trim();
        if (type === "int" && !/^[+-]?\d+$/.test(normalized)) {
          callback(new Error(t("systemSetting.invalidInt")));
        } else if (
          type === "float" &&
          (normalized === "" || !Number.isFinite(Number(normalized)))
        ) {
          callback(new Error(t("systemSetting.invalidFloat")));
        } else if (type === "json") {
          try {
            JSON.parse(normalized);
            callback();
          } catch {
            callback(new Error(t("systemSetting.invalidJson")));
          }
        } else {
          callback();
        }
      },
      trigger: "blur"
    }
  ]
}));

function openEditor(setting: SystemSettingItem) {
  editingSetting.value = setting;
  form.boolValue = setting.value.trim().toLowerCase() === "true";
  if (setting.value_type === "json") {
    try {
      form.value = JSON.stringify(JSON.parse(setting.value), null, 2);
    } catch {
      form.value = setting.value;
    }
  } else {
    form.value = setting.value;
  }
  dialogVisible.value = true;
}

async function saveSetting() {
  if (!editingSetting.value) return;
  if (editingSetting.value.value_type !== "bool") {
    await formRef.value?.validate();
  }

  saving.value = true;
  try {
    const value =
      editingSetting.value.value_type === "bool"
        ? String(form.boolValue)
        : form.value;
    await updateSystemSetting(editingSetting.value.key, value);
    ElMessage.success(t("messages.saveSuccess"));
    dialogVisible.value = false;
    await fetchSettings();
  } finally {
    saving.value = false;
  }
}

fetchSettings();
</script>

<style scoped>
.search-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.setting-value {
  display: block;
  overflow: hidden;
  font-family: Consolas, "Courier New", monospace;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.description-text {
  line-height: 1.5;
  color: var(--el-text-color-regular);
}

.json-editor :deep(textarea) {
  font-family: Consolas, "Courier New", monospace;
  line-height: 1.5;
}

@media (width <= 640px) {
  :deep(.el-dialog) {
    width: 94% !important;
  }
}
</style>
