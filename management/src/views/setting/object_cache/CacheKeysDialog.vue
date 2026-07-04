<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { CacheStatsItem } from "@/api/object_cache";

const props = defineProps<{
  visible: boolean;
  cache: CacheStatsItem | null;
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "refresh"): void;
  (e: "invalidate-key", key: any): Promise<boolean> | void;
  (e: "invalidate-everywhere", key: any): void;
}>();

const { t } = useI18n();

const dialogVisible = computed({
  get: () => props.visible,
  set: val => emit("update:visible", val)
});

const keyFilter = ref("");
const everywhereMode = ref(false);
const invalidatingKey = ref<string | null>(null);

/** 将 key 统一格式化为可展示 / 可提交的字符串或原始结构 */
function displayKey(key: any): string {
  return typeof key === "string" ? key : JSON.stringify(key);
}

const filteredKeys = computed(() => {
  const keys = props.cache?.keys ?? [];
  if (!keyFilter.value) return keys;
  return keys.filter(k =>
    displayKey(k).toLowerCase().includes(keyFilter.value.toLowerCase())
  );
});

async function onInvalidateOne(key: any) {
  invalidatingKey.value = displayKey(key);
  try {
    if (everywhereMode.value) {
      emit("invalidate-everywhere", key);
    } else {
      const result = emit("invalidate-key", key);
      if (result instanceof Promise) await result;
    }
    emit("refresh");
  } finally {
    invalidatingKey.value = null;
  }
}

watch(
  () => props.visible,
  visible => {
    if (!visible) {
      keyFilter.value = "";
      everywhereMode.value = false;
    }
  }
);
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    :title="cache ? `${cache.name}` : ''"
    width="640px"
    destroy-on-close
  >
    <div v-if="cache" class="cache-keys-dialog">
      <div class="cache-keys-dialog__meta">
        <el-tag type="info">{{ t("cache.size") }}: {{ cache.size }}</el-tag>
        <span class="cache-keys-dialog__desc">{{ cache.description }}</span>
      </div>

      <div class="cache-keys-dialog__toolbar">
        <el-input
          v-model="keyFilter"
          :placeholder="t('cache.searchKeyPlaceholder')"
          clearable
          style="width: 240px"
        />
        <el-checkbox v-model="everywhereMode">
          {{ t("cache.invalidateEverywhereMode") }}
        </el-checkbox>
      </div>

      <el-table :data="filteredKeys" max-height="360" size="small">
        <el-table-column :label="t('cache.key')">
          <template #default="{ row }">
            <span class="cache-keys-dialog__key">{{ displayKey(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          :label="t('labels.operation')"
          width="120"
          align="right"
        >
          <template #default="{ row }">
            <el-popconfirm
              :title="t('cache.confirmInvalidateKey')"
              @confirm="onInvalidateOne(row)"
            >
              <template #reference>
                <el-button
                  link
                  type="danger"
                  :loading="invalidatingKey === displayKey(row)"
                >
                  {{ t("cache.invalidate") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!filteredKeys.length"
        :description="t('cache.noKeys')"
        :image-size="80"
      />
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">{{
        t("buttons.close")
      }}</el-button>
      <el-button type="primary" @click="emit('refresh')">
        {{ t("buttons.refresh") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped lang="scss">
.cache-keys-dialog {
  &__meta {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
  }

  &__desc {
    color: var(--el-text-color-secondary);
    font-size: 13px;
  }

  &__toolbar {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 12px;
  }

  &__key {
    font-family: var(--el-font-family-mono, monospace);
    word-break: break-all;
  }
}
</style>
