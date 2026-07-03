<script setup lang="ts">
import { useI18n } from "vue-i18n";
import PureTableBar from "@/components/RePureTableBar/src/bar";
import { useCache } from "./utils/hook";
import CacheKeysDialog from "./CacheKeysDialog.vue";

defineOptions({
  name: "CacheManagement"
});

const { t } = useI18n();

const {
  loading,
  dataList,
  columns,
  keysDialogVisible,
  currentCache,
  onSearch,
  openKeysDialog,
  refreshCurrentCache,
  handleInvalidateAll,
  handleInvalidateKey,
  handleInvalidateEverywhere
} = useCache();
</script>

<template>
  <div class="main">
    <PureTableBar
      :title="t('cache.title')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button
          v-auth="'system:cache:list'"
          type="primary"
          @click="onSearch"
        >
          {{ t("buttons.refresh") }}
        </el-button>
      </template>

      <template v-slot="{ size, dynamicColumns }">
        <pure-table
          border
          adaptive
          :size="size"
          :loading="loading"
          :data="dataList"
          :columns="dynamicColumns"
          row-key="name"
        >
          <template #operation="{ row }">
            <el-button
              v-auth="'system:cache:list'"
              link
              type="primary"
              :size="size"
              @click="openKeysDialog(row)"
            >
              {{ t("cache.viewKeys") }}
            </el-button>
            <el-popconfirm
              :title="t('cache.confirmInvalidateAll', { name: row.name })"
              @confirm="handleInvalidateAll(row)"
            >
              <template #reference>
                <el-button
                  v-auth="'system:cache:invalidate'"
                  link
                  type="danger"
                  :size="size"
                >
                  {{ t("cache.invalidateAll") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <CacheKeysDialog
      v-model:visible="keysDialogVisible"
      :cache="currentCache"
      @refresh="refreshCurrentCache"
      @invalidate-key="key => handleInvalidateKey(currentCache!.name, key)"
      @invalidate-everywhere="handleInvalidateEverywhere"
    />
  </div>
</template>
