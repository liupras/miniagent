<script setup lang="ts">
import { useI18n } from "vue-i18n";
import PureTableBar from "@/components/RePureTableBar/src/bar";
import { useCacheStore } from "./utils/hook";
import NamespaceKeysDialog from "./NamespaceKeysDialog.vue";

defineOptions({
  name: "CacheStoreManagement"
});

const { t } = useI18n();

const {
  loading,
  dataList,
  columns,
  keysDialogVisible,
  currentNamespace,
  onSearch,
  openKeysDialog,
  refreshCurrentNamespace,
  handleClearNamespace,
  handleClearAll,
  handleDeleteKeys
} = useCacheStore();
</script>

<template>
  <div class="main">
    <PureTableBar
      :title="t('valueCache.title')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button v-auth="'value_cache:edit'" type="primary" @click="onSearch">
          {{ t("buttons.refresh") }}
        </el-button>
        <el-button
          v-auth="'value_cache:edit'"
          type="danger"
          plain
          @click="handleClearAll"
        >
          {{ t("valueCache.clearAll") }}
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
          row-key="namespace"
        >
          <template #operation="{ row }">
            <el-button
              v-auth="'value_cache:list'"
              link
              type="primary"
              :size="size"
              @click="openKeysDialog(row)"
            >
              {{ t("valueCache.viewKeys") }}
            </el-button>
            <el-popconfirm
              :title="
                t('valueCache.confirmClear', { namespace: row.namespace })
              "
              @confirm="handleClearNamespace(row)"
            >
              <template #reference>
                <el-button
                  v-auth="'value_cache:edit'"
                  link
                  type="danger"
                  :size="size"
                >
                  {{ t("buttons.clear") }}
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </pure-table>
      </template>
    </PureTableBar>

    <NamespaceKeysDialog
      v-model:visible="keysDialogVisible"
      :namespace="currentNamespace"
      @refresh="refreshCurrentNamespace"
      @delete-keys="keys => handleDeleteKeys(currentNamespace!.namespace, keys)"
    />
  </div>
</template>
