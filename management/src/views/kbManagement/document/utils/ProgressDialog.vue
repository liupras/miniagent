<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import type { ProgressState } from "./types";

const props = defineProps<{ modelValue: ProgressState }>();
const emit = defineEmits<{ close: [] }>();

const { t } = useI18n();

const status = computed(() => {
  if (props.modelValue.error) return "exception";
  if (props.modelValue.done) return "success";
  return undefined;
});

const canClose = computed(
  () => props.modelValue.done || props.modelValue.error
);

function handleClose() {
  if (!canClose.value) return; // keep the dialog pinned open while a task is running
  emit("close");
}
</script>

<template>
  <el-dialog
    :model-value="modelValue.visible"
    :title="t(`document.progress.title.${modelValue.mode}`)"
    width="480px"
    :close-on-click-modal="false"
    :close-on-press-escape="canClose"
    :show-close="canClose"
    @close="handleClose"
  >
    <el-progress
      :percentage="Math.min(100, Math.round(modelValue.progress))"
      :status="status"
      :stroke-width="14"
    />

    <div v-if="modelValue.stage" class="progress-stage">
      {{ t("document.progress.stage") }}: {{ modelValue.stage }}
    </div>

    <el-alert
      class="progress-message"
      :type="modelValue.error ? 'error' : modelValue.done ? 'success' : 'info'"
      :title="modelValue.message"
      :closable="false"
      show-icon
    />

    <template #footer>
      <el-button :disabled="!canClose" type="primary" @click="handleClose">
        {{ t("buttons.close") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.progress-stage {
  margin-top: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.progress-message {
  margin-top: 12px;
}
</style>
