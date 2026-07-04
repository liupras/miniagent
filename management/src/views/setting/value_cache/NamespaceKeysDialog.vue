<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import { getCacheStoreKeys, type CacheStoreStatsItem } from "@/api/value_cache";

const props = defineProps<{
  visible: boolean;
  namespace: CacheStoreStatsItem | null;
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "refresh"): void;
  (e: "delete-keys", keys: string[]): Promise<number> | void;
}>();

const { t } = useI18n();

const dialogVisible = computed({
  get: () => props.visible,
  set: val => emit("update:visible", val)
});

const prefixFilter = ref("");
const limit = ref(100);
const keys = ref<string[]>([]);
const truncated = ref(false);
const loading = ref(false);
const deleting = ref(false);
const selectedKeys = ref<string[]>([]);

async function loadKeys() {
  if (!props.namespace) return;
  loading.value = true;
  try {
    const data = await getCacheStoreKeys(props.namespace.namespace, {
      prefix: prefixFilter.value || undefined,
      limit: limit.value
    });
    keys.value = data.keys;
    truncated.value = data.truncated;
    selectedKeys.value = [];
  } finally {
    loading.value = false;
  }
}

function onSelectionChange(rows: string[]) {
  selectedKeys.value = rows;
}

async function onDeleteSelected() {
  if (!selectedKeys.value.length) return;
  deleting.value = true;
  try {
    const result = emit("delete-keys", selectedKeys.value);
    if (result instanceof Promise) await result;
    await loadKeys();
    emit("refresh");
  } finally {
    deleting.value = false;
  }
}

watch(
  () => props.visible,
  visible => {
    if (visible) {
      prefixFilter.value = "";
      loadKeys();
    } else {
      keys.value = [];
      selectedKeys.value = [];
    }
  }
);
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="namespace ? `${t('valueCache.keysOf')} ${namespace.namespace}` : ''"
    width="640px"
    destroy-on-close
  >
    <div v-if="namespace" class="namespace-keys-dialog">
      <div class="namespace-keys-dialog__meta">
        <el-tag type="info">
          {{ t("valueCache.backendType") }}: {{ namespace.backend_type }}
        </el-tag>
        <el-tag type="info">
          {{ t("valueCache.size") }}: {{ namespace.size ?? "-" }}
        </el-tag>
      </div>

      <div class="namespace-keys-dialog__toolbar">
        <el-input
          v-model="prefixFilter"
          :placeholder="t('valueCache.prefixPlaceholder')"
          clearable
          style="width: 220px"
          @keyup.enter="loadKeys"
        />
        <el-button :loading="loading" @click="loadKeys">
          {{ t("buttons.refresh") }}
        </el-button>
        <el-popconfirm
          :title="
            t('valueCache.confirmDeleteSelected', {
              count: selectedKeys.length
            })
          "
          @confirm="onDeleteSelected"
        >
          <template #reference>
            <el-button
              type="danger"
              :disabled="!selectedKeys.length"
              :loading="deleting"
            >
              {{ t("valueCache.deleteSelected") }}
            </el-button>
          </template>
        </el-popconfirm>
      </div>

      <el-table
        v-loading="loading"
        :data="keys"
        max-height="360"
        size="small"
        @selection-change="rows => onSelectionChange(rows as string[])"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column :label="t('valueCache.key')">
          <template #default="{ row }">
            <span class="namespace-keys-dialog__key">{{ row }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && !keys.length"
        :description="t('valueCache.noKeys')"
        :image-size="80"
      />
      <div v-if="truncated" class="namespace-keys-dialog__truncated">
        {{ t("valueCache.truncatedHint", { limit }) }}
      </div>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">
        {{ t("buttons.close") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.namespace-keys-dialog {
  &__meta {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  &__toolbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  &__key {
    font-family: var(--el-font-family-mono, monospace);
    word-break: break-all;
  }

  &__truncated {
    margin-top: 8px;
    font-size: 12px;
    color: var(--el-text-color-secondary);
  }
}
</style>
