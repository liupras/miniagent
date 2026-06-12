<template>
  <div class="main">
    <el-form
      ref="searchFormRef"
      :inline="true"
      :model="searchForm"
      class="search-form bg-bg_color w-[99/100] pl-8 pt-3 overflow-auto"
    >
      <el-form-item :label="t('strategyConfig.basic.kbName')" prop="kb_id">
        <el-select
          v-model="searchForm.kb_id"
          clearable
          :placeholder="t('strategyConfig.kbNamePlaceholder')"
          class="w-50!"
          @change="onSearch"
        >
          <el-option
            v-for="item in kbOptions"
            :key="item.id"
            :label="item.name"
            :value="item.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button
          v-auth="'strategy_config:list'"
          type="primary"
          :icon="Search"
          @click="onSearch"
        >
          {{ t("buttons.search") }}
        </el-button>
        <el-button
          v-auth="'strategy_config:list'"
          :icon="Refresh"
          @click="onReset"
        >
          {{ t("buttons.reset") }}
        </el-button>
      </el-form-item>
    </el-form>

    <PureTableBar
      :title="t('strategyConfig.tableTitle')"
      :columns="columns"
      @refresh="onSearch"
    >
      <template #buttons>
        <el-button
          v-auth="'strategy_config:add'"
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
          row-key="config_id"
          :data="tableData"
          :columns="dynamicColumns"
          :size="size"
          :loading="loading"
          :pagination="pagination"
          align-whole="center"
          @page-current-change="handleCurrentChange"
          @page-size-change="handleSizeChange"
        >
          <template #is_active="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'">
              {{
                row.is_active ? t("common.activated") : t("common.deactivated")
              }}
            </el-tag>
          </template>

          <template #operation="{ row }">
            <el-button
              v-auth="'strategy_config:edit'"
              link
              type="primary"
              :disabled="row.is_active"
              @click="handleActivate(row)"
            >
              {{ t("buttons.active") }}
            </el-button>
            <el-button
              v-auth="'strategy_config:edit'"
              link
              type="primary"
              :icon="EditPen"
              @click="openDialog('edit', row)"
            >
              {{ t("buttons.edit") }}
            </el-button>
            <el-popconfirm
              :title="t('common.deleteConfirm')"
              @confirm="onDelete(row)"
            >
              <template #reference>
                <el-button
                  v-auth="'strategy_config:delete'"
                  link
                  type="danger"
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
      :title="
        dialogType === 'add'
          ? t('strategyConfig.new')
          : t('strategyConfig.edit')
      "
      width="850px"
      top="5vh"
    >
      <el-form
        ref="dialogFormRef"
        :model="dialogForm"
        :rules="formRules"
        label-width="190px"
        label-position="right"
      >
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="t('strategyConfig.basic.title')" name="basic">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item
                  :label="t('strategyConfig.basic.configId')"
                  prop="config_id"
                >
                  <el-input
                    v-model="dialogForm.config_id"
                    :disabled="dialogType === 'edit'"
                    placeholder="max 100 chars"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item
                  :label="t('strategyConfig.basic.kbName')"
                  prop="kb_id"
                >
                  <el-select
                    v-model="dialogForm.kb_id"
                    :disabled="dialogType === 'edit'"
                    placeholder="t('strategyConfig.basic.kbNamePlaceholder')"
                    class="w-full"
                  >
                    <el-option
                      v-for="item in kbOptions"
                      :key="item.id"
                      :label="item.name"
                      :value="item.id"
                    />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item
                  :label="t('strategyConfig.basic.version')"
                  prop="version"
                >
                  <el-input-number
                    v-model="dialogForm.version"
                    :min="1"
                    class="w-full"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item
                  :label="t('strategyConfig.basic.promptLanguage')"
                  prop="prompt_language"
                >
                  <el-select
                    v-model="dialogForm.prompt_language"
                    clearable
                    class="w-full"
                  >
                    <el-option label="中文 (zh)" value="zh" />
                    <el-option label="English (en)" value="en" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-divider content-position="left">{{
              t("strategyConfig.switches.title")
            }}</el-divider>

            <el-row :gutter="10">
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableQueryRewrite')"
                >
                  <el-switch v-model="dialogForm.enable_query_rewrite" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableQueryExpansion')"
                >
                  <el-switch v-model="dialogForm.enable_query_expansion" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableQueryHyde')"
                >
                  <el-switch v-model="dialogForm.enable_query_hyde" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableVector')"
                >
                  <el-switch v-model="dialogForm.enable_vector" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableBm25')"
                >
                  <el-switch v-model="dialogForm.enable_bm25" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableReranker')"
                >
                  <el-switch v-model="dialogForm.enable_reranker" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.enableSmallToBig')"
                >
                  <el-switch v-model="dialogForm.enable_small_to_big" />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item
                  label-width="140px"
                  :label="t('strategyConfig.switches.requireCitation')"
                >
                  <el-switch v-model="dialogForm.require_citation" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-tab-pane>

          <el-tab-pane :label="t('strategyConfig.params.title')" name="params">
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item
                  :label="t('strategyConfig.params.queryExpansionNum')"
                >
                  <el-input-number
                    v-model="dialogForm.query_expansion_num"
                    :min="1"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item
                  :label="t('strategyConfig.params.maxTransformQueries')"
                >
                  <el-input-number
                    v-model="dialogForm.max_transform_queries"
                    :min="1"
                  />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.vectorTopK')">
                  <el-input-number v-model="dialogForm.vector_top_k" :min="1" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.bm25TopK')">
                  <el-input-number v-model="dialogForm.bm25_top_k" :min="1" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.rrfMode')">
                  <el-select v-model="dialogForm.rrf_mode" class="w-full">
                    <el-option label="RRF" value="rrf" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.rrfK')">
                  <el-input-number v-model="dialogForm.rrf_k" :min="1" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.rrfTopK')">
                  <el-input-number v-model="dialogForm.rrf_top_k" :min="1" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.rerankingMode')">
                  <el-select v-model="dialogForm.reranking_mode" class="w-full">
                    <el-option label="Vector" value="vector" />
                    <el-option label="BM25" value="bm25" />
                    <el-option label="Hybrid" value="hybrid" />
                    <el-option label="Rerank" value="rerank" />
                    <el-option label="LLM" value="llm" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="20">
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.rerankTopK')">
                  <el-input-number v-model="dialogForm.rerank_top_k" :min="1" />
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item :label="t('strategyConfig.params.finalTopK')">
                  <el-input-number v-model="dialogForm.final_top_k" :min="1" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item :label="t('strategyConfig.params.vectorWeight')">
              <el-slider
                v-model="dialogForm.vector_weight"
                :max="1"
                :min="0"
                :step="0.05"
                show-input
              />
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane
            :label="t('strategyConfig.thresholds.title')"
            name="threshold"
          >
            <el-form-item
              :label="t('strategyConfig.thresholds.vectorScoreThreshold')"
            >
              <el-input-number
                v-model="dialogForm.vector_score_threshold"
                :step="0.05"
                :min="0"
                :max="1"
              />
            </el-form-item>
            <el-form-item
              :label="t('strategyConfig.thresholds.bm25ScoreThreshold')"
            >
              <el-input-number
                v-model="dialogForm.bm25_score_threshold"
                :step="0.05"
                :min="0"
                :max="1"
              />
            </el-form-item>
            <el-form-item
              :label="t('strategyConfig.thresholds.highScoreThreshold')"
            >
              <el-input-number
                v-model="dialogForm.confidence_high_score_threshold"
                :step="0.05"
                :min="0"
                :max="1"
              />
            </el-form-item>
            <el-form-item
              :label="t('strategyConfig.thresholds.minHighConfCount')"
            >
              <el-input-number
                v-model="dialogForm.confidence_min_high_conf_count"
                :min="0"
              />
            </el-form-item>
            <el-form-item
              :label="t('strategyConfig.thresholds.lowScoreThreshold')"
            >
              <el-input-number
                v-model="dialogForm.confidence_low_score_threshold"
                :step="0.05"
                :min="0"
                :max="1"
              />
            </el-form-item>
          </el-tab-pane>

          <el-tab-pane :label="t('strategyConfig.extra.title')" name="extra">
            <el-form-item label-width="0" prop="extra_config">
              <el-input
                v-model="extraConfigStr"
                type="textarea"
                :rows="12"
                placeholder='t("strategyConfig.extra.placeholder")'
              />
            </el-form-item>
          </el-tab-pane>
        </el-tabs>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">{{
          t("buttons.cancel")
        }}</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="onSubmit">{{
          t("buttons.confirm")
        }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { useI18n } from "vue-i18n";
import { ElMessage } from "element-plus";
import type { FormInstance, FormRules } from "element-plus";
import { PureTableBar } from "@/components/RePureTableBar";
import {
  getStrategyList,
  createStrategy,
  updateStrategy,
  activateStrategy,
  deleteStrategy,
  getKnowledgeBaseOptions,
  type KnowledgeBaseOption
} from "@/api/strategy_config";

// Icons
import Search from "~icons/ep/search";
import Refresh from "~icons/ep/refresh";
import Plus from "~icons/ep/plus";
import Delete from "~icons/ep/delete";
import EditPen from "~icons/ep/edit-pen";
import { hasAuth } from "@/router/utils";

const { t } = useI18n();

// Refs
const dialogFormRef = ref<FormInstance>();

// Loading & Visibility states
const loading = ref(false);
const dialogLoading = ref(false);
const dialogVisible = ref(false);
const dialogType = ref<"add" | "edit">("add");
const activeTab = ref("basic");

// Pagination & Data states
const tableData = ref([]);
const kbOptions = ref<KnowledgeBaseOption[]>([]);
const extraConfigStr = ref("{}");

// 优化3: 默认搜索设置为 null，实现无感查询全部策略
const searchForm = reactive({ kb_id: null });

const pagination = reactive({
  total: 0,
  pageSize: 20,
  currentPage: 1,
  background: true
});

// 全量默认初始值（严格映射 Pydantic 默认参数）
const defaultFormData = {
  config_id: "",
  kb_id: null as number, // 初始化为 null 提示用户必须通过下拉框选择
  version: 1,
  prompt_language: "zh",
  enable_query_rewrite: true,
  enable_query_expansion: false,
  enable_query_hyde: false,
  enable_vector: true,
  enable_bm25: true,
  enable_reranker: true,
  enable_small_to_big: true,
  require_citation: true,
  query_expansion_num: 3,
  max_transform_queries: 5,
  vector_top_k: 30,
  bm25_top_k: 30,
  rrf_mode: "rrf",
  rrf_k: 60,
  rrf_top_k: 20,
  vector_weight: 0.6,
  reranking_mode: "hybrid",
  rerank_top_k: 10,
  final_top_k: 3,
  vector_score_threshold: 0.5,
  bm25_score_threshold: 0.1,
  confidence_high_score_threshold: 0.7,
  confidence_min_high_conf_count: 1,
  confidence_low_score_threshold: 0.5,
  extra_config: null
};

const dialogForm = reactive({ ...defaultFormData });

// Form validation rules
const formRules = reactive<FormRules>({
  config_id: [
    {
      required: true,
      message: "t('strategyConfig.basic.configIdRequired')",
      trigger: "blur"
    },
    {
      max: 100,
      message: "t('strategyConfig.basic.configIdRequired')",
      trigger: "blur"
    }
  ],
  kb_id: [
    {
      required: true,
      message: "t('strategyConfig.basic.kbIdRequired')",
      trigger: "change" // 下拉选择校验触发规则变更为 change
    }
  ],
  version: [
    {
      required: true,
      message: "t('strategyConfig.basic.versionRequired')",
      trigger: "blur"
    }
  ]
});

// Table columns mapping
const columns: TableColumnList = [
  {
    label: t('strategyConfig.basic.configId'),
    prop: "config_id",
    width: 140,
    align: "left"
  },
  {
    label: t("strategyConfig.basic.kbName"),
    prop: "kb_id",
    width: 150,
    formatter: ({ kb_id }) => {
      const option = kbOptions.value.find(item => item.id === kb_id);
      return option ? option.name : `ID: ${kb_id}`;
    }
  },
  { label: t("strategyConfig.basic.version"), prop: "version", width: 90 },
  {
    label: t("strategyConfig.basic.promptLanguage"),
    prop: "prompt_language",
    width: 130
  },
  {
    label: t("strategyConfig.basic.isActive"),
    prop: "is_active",
    slot: "is_active",
    width: 110
  },
  {
    label: t("common.createdAt") || "Created At",
    prop: "created_at",
    width: 180,
    formatter: ({ created_at }) =>
      created_at
        ? new Date(created_at).toLocaleString("zh-CN", {
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
    slot: "operation",
    fixed: "right",
    width: 220,
    hide: !hasAuth("strategy_config:edit") && !hasAuth("strategy_config:delete")
  }
];

// Actions & Handlers

/** 获取知识库下拉选项 */
async function fetchKbOptions() {
  try {
    const res = await getKnowledgeBaseOptions();
    //console.log(res);
    if (res) {
      kbOptions.value = res;
    }
  } catch (error) {
    console.error("t('strategyConfig.kbLoadError'):", error);
  }
}

async function fetchData() {
  loading.value = true;
  try {
    // 完美的单点统一调用
    const res: any = await getStrategyList(searchForm.kb_id, {
      page: pagination.currentPage,
      page_size: pagination.pageSize
    });
    console.log(res.items);

    if (res) {
      tableData.value = res.items || [];
      pagination.total = res.total || 0;
    }
  } catch (error) {
    console.error(error);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  pagination.currentPage = 1;
  fetchData();
}

// 优化5: 重置将 kb_id 归于 null 状态从而刷新出全量列表
function onReset() {
  searchForm.kb_id = null;
  pagination.currentPage = 1;
  fetchData();
}

function handleCurrentChange(val: number) {
  pagination.currentPage = val;
  fetchData();
}

function handleSizeChange(val: number) {
  pagination.pageSize = val;
  pagination.currentPage = 1;
  fetchData();
}

function openDialog(type: "add" | "edit", row?: any) {
  dialogType.value = type;
  activeTab.value = "basic";

  if (type === "edit" && row) {
    Object.assign(dialogForm, row);
    extraConfigStr.value = JSON.stringify(row.extra_config || {}, null, 2);
  } else {
    Object.assign(dialogForm, defaultFormData);
    extraConfigStr.value = "{}";
  }
  dialogVisible.value = true;
}

async function handleActivate(row: any) {
  loading.value = true;
  try {
    await activateStrategy(row.config_id);
    ElMessage.success(
      t("strategyConfig.activeSuccess") || "Activated successfully"
    );
    fetchData();
  } catch (error) {
    console.error(error);
  } finally {
    loading.value = false;
  }
}

function validateJsonField(): boolean {
  try {
    if (!extraConfigStr.value.trim()) {
      dialogForm.extra_config = null;
      return true;
    }
    dialogForm.extra_config = JSON.parse(extraConfigStr.value);
    return true;
  } catch (e) {
    ElMessage.error("t('common.jsonFormatError')");
    activeTab.value = "extra";
    return false;
  }
}

async function onSubmit() {
  if (!dialogFormRef.value) return;

  const valid = await dialogFormRef.value.validate();
  if (!valid || !validateJsonField()) return;

  dialogLoading.value = true;
  try {
    if (dialogType.value === "add") {
      await createStrategy(dialogForm as any);
      ElMessage.success(t("common.addSuccess"));
    } else {
      await updateStrategy(dialogForm.config_id, dialogForm);
      ElMessage.success(t("common.editSuccess"));
    }
    dialogVisible.value = false;
    fetchData();
  } catch (error) {
    console.error(error);
  } finally {
    dialogLoading.value = false;
  }
}

async function onDelete(row: any) {
  loading.value = true;
  try {
    await deleteStrategy(row.config_id);
    ElMessage.success(t("common.deleteSuccess"));
    fetchData();
  } catch (error) {
    console.error(error);
  } finally {
    loading.value = false;
  }
}

// 初始化时：并行动调选项获取和业务列表加载
onMounted(async () => {
  await fetchKbOptions();
  fetchData();
});
</script>

<style scoped>
.search-form {
  margin-bottom: 12px;
  border-radius: 4px;
}
:deep(.el-divider--horizontal) {
  margin: 18px 0;
}
</style>
