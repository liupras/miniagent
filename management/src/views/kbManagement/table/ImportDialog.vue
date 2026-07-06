<script setup lang="ts">
defineOptions({
  name: "ImportDialog"
});

import { ref, reactive, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  ElMessage,
  type UploadUserFile,
  type UploadInstance
} from "element-plus";
import {
  importTable,
  isExcelFile,
  IMPORT_ACCEPT_EXTENSIONS,
  type ImportTableResult
} from "@/api/tables";

const props = defineProps<{
  modelValue: boolean;
  /** Schema pre-selected from the parent's schema switcher. */
  schemaName: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: boolean): void;
  (e: "success", result: ImportTableResult): void;
}>();

const { t } = useI18n();

const visible = computed({
  get: () => props.modelValue,
  set: value => emit("update:modelValue", value)
});

const uploadRef = ref<UploadInstance>();
const submitting = ref(false);

const form = reactive({
  schemaName: props.schemaName,
  tableName: "",
  sheetName: "",
  primaryKey: "",
  forceCast: false,
  allowNewColumns: false
});

const selectedFile = ref<File | null>(null);
const isExcelSelected = computed(() =>
  selectedFile.value ? isExcelFile(selectedFile.value.name) : false
);

// Re-sync default schema whenever the dialog is (re)opened.
watch(visible, open => {
  if (open) resetForm();
});

function resetForm() {
  form.schemaName = props.schemaName || "main";
  form.tableName = "";
  form.sheetName = "";
  form.primaryKey = "";
  form.forceCast = false;
  form.allowNewColumns = false;
  selectedFile.value = null;
  uploadRef.value?.clearFiles();
}

function handleFileChange(uploadFile: UploadUserFile) {
  selectedFile.value = (uploadFile.raw as File) ?? null;
  if (selectedFile.value && !form.tableName) {
    form.tableName = selectedFile.value.name.replace(/\.[^.]+$/, "");
  }
}

function handleFileRemove() {
  selectedFile.value = null;
}

async function handleConfirm() {
  if (!selectedFile.value) {
    ElMessage.warning(t("tableManagement.selectFileFirst"));
    return;
  }
  submitting.value = true;
  try {
    const result = await importTable({
      file: selectedFile.value,
      schemaName: form.schemaName,
      tableName: form.tableName || undefined,
      sheetName: isExcelSelected.value
        ? form.sheetName || undefined
        : undefined,
      primaryKey: form.primaryKey || undefined,
      forceCast: form.forceCast,
      allowNewColumns: form.allowNewColumns
    });
    ElMessage.success(
      t("tableManagement.importSuccess", { tablePath: result.tablePath })
    );
    visible.value = false;
    emit("success", result);
  } finally {
    submitting.value = false;
  }
}

function handleCancel() {
  visible.value = false;
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="t('tableManagement.importTitle')"
    width="520px"
    destroy-on-close
  >
    <el-form :model="form" label-width="120px">
      <el-form-item :label="t('tableManagement.uploadFile')" required>
        <el-upload
          ref="uploadRef"
          drag
          :auto-upload="false"
          :limit="1"
          :accept="IMPORT_ACCEPT_EXTENSIONS"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
        >
          <div>{{ t("tableManagement.uploadHint") }}</div>
        </el-upload>
      </el-form-item>

      <el-form-item :label="t('tableManagement.schema')">
        <el-input v-model="form.schemaName" />
      </el-form-item>

      <el-form-item :label="t('tableManagement.table')">
        <el-input v-model="form.tableName" />
      </el-form-item>

      <el-form-item
        v-if="isExcelSelected"
        :label="t('tableManagement.sheetName')"
      >
        <el-input
          v-model="form.sheetName"
          :placeholder="t('tableManagement.sheetNamePlaceholder')"
        />
      </el-form-item>

      <el-form-item :label="t('tableManagement.primaryKey')">
        <el-input
          v-model="form.primaryKey"
          :placeholder="t('tableManagement.primaryKeyPlaceholder')"
        />
      </el-form-item>

      <el-form-item :label="t('tableManagement.forceCast')">
        <el-switch v-model="form.forceCast" />
      </el-form-item>

      <el-form-item :label="t('tableManagement.allowNewColumns')">
        <el-switch v-model="form.allowNewColumns" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleCancel">{{ t("buttons.cancel") }}</el-button>
      <el-button type="primary" :loading="submitting" @click="handleConfirm">
        {{ t("buttons.confirm") }}
      </el-button>
    </template>
  </el-dialog>
</template>
