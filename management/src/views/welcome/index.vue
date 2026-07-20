<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import dayjs from "dayjs";
import Plus from "~icons/ep/plus";
import Cpu from "~icons/ep/cpu";
import Collection from "~icons/ep/collection";
import UploadFilled from "~icons/ep/upload-filled";
import Grid from "~icons/ep/grid";
import Connection from "~icons/ep/connection";
import DataAnalysis from "~icons/ep/data-analysis";
import Refresh from "~icons/ep/refresh";
import Monitor from "~icons/ep/monitor";
import Coin from "~icons/ep/coin";
import FolderOpened from "~icons/ep/folder-opened";
import { hasPerms } from "@/utils/auth";
import {
  getSystemStatus,
  type HealthStatus,
  type SystemStatusResult
} from "@/api/system_status";

defineOptions({ name: "Welcome" });

const { t } = useI18n();
const router = useRouter();
const loading = ref(false);
const systemStatus = ref<SystemStatusResult | null>(null);
const canViewStatus = computed(() => hasPerms("system_setting:list"));

const quickActions = [
  {
    key: "agent",
    path: "/agentManagement/agent",
    permission: "agent:add",
    action: "create",
    icon: Cpu,
    color: "#409eff"
  },
  {
    key: "knowledgeBase",
    path: "/kbManagement/knowledge_base",
    permission: "knowledge_base:add",
    action: "create",
    icon: Collection,
    color: "#67c23a"
  },
  {
    key: "document",
    path: "/kbManagement/document",
    permission: "document:add",
    action: "upload",
    icon: UploadFilled,
    color: "#e6a23c"
  },
  {
    key: "table",
    path: "/kbManagement/table",
    permission: "table:add",
    action: "upload",
    icon: Grid,
    color: "#9b59b6"
  },
  {
    key: "llm",
    path: "/setting/llm",
    permission: "llm:add",
    action: "create",
    icon: Connection,
    color: "#f56c6c"
  },
  {
    key: "embedding",
    path: "/setting/embedding",
    permission: "embedding:add",
    action: "create",
    icon: DataAnalysis,
    color: "#00a8a8"
  }
];

const componentOrder = ["api", "sqlite", "duckdb"] as const;

const statusTagType = (status: HealthStatus) =>
  ({
    healthy: "success",
    degraded: "warning",
    unhealthy: "danger",
    not_configured: "info"
  })[status] as "success" | "warning" | "danger" | "info";

const progressStatus = (value: number) =>
  value >= 90 ? "exception" : value >= 75 ? "warning" : "success";

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    units.length - 1
  );
  return `${(value / 1024 ** index).toFixed(index > 2 ? 1 : 0)} ${units[index]}`;
}

function openQuickAction(item: (typeof quickActions)[number]) {
  if (!hasPerms(item.permission)) {
    ElMessage.warning(t("welcome.quickActions.noPermission"));
    return;
  }
  void router.push({
    path: item.path,
    query: {
      quickAction: item.action,
      quickActionId: String(Date.now())
    }
  });
}

async function refreshStatus(showError = true) {
  if (!canViewStatus.value) return;
  loading.value = true;
  try {
    systemStatus.value = await getSystemStatus();
  } catch {
    if (showError) ElMessage.error(t("welcome.status.loadFailed"));
  } finally {
    loading.value = false;
  }
}

let refreshTimer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  void refreshStatus();
  refreshTimer = setInterval(() => void refreshStatus(false), 60_000);
});
onBeforeUnmount(() => clearInterval(refreshTimer));
</script>

<template>
  <div class="welcome-page">
    <section class="hero-panel">
      <div>
        <div class="hero-eyebrow">MINI AGENT CONSOLE</div>
        <h1>{{ t("welcome.title") }}</h1>
        <p>{{ t("welcome.subtitle") }}</p>
      </div>
      <div v-if="systemStatus" class="hero-meta">
        <el-tag :type="statusTagType(systemStatus.status)" effect="dark" round>
          {{ t(`welcome.status.values.${systemStatus.status}`) }}
        </el-tag>
        <span
          >v{{ systemStatus.version }} · {{ systemStatus.environment }}</span
        >
      </div>
    </section>

    <el-card shadow="never" class="panel-card quick-panel">
      <template #header>
        <div class="panel-title">
          <div>
            <h2>{{ t("welcome.quickActions.title") }}</h2>
            <p>{{ t("welcome.quickActions.subtitle") }}</p>
          </div>
        </div>
      </template>
      <div class="quick-grid">
        <button
          v-for="item in quickActions"
          :key="item.key"
          class="quick-item"
          :class="{ disabled: !hasPerms(item.permission) }"
          type="button"
          @click="openQuickAction(item)"
        >
          <span class="quick-icon" :style="{ color: item.color }">
            <component :is="item.icon" />
          </span>
          <span class="quick-copy">
            <strong>{{ t(`welcome.quickActions.items.${item.key}`) }}</strong>
            <small>{{
              t(`welcome.quickActions.descriptions.${item.key}`)
            }}</small>
          </span>
          <Plus class="quick-plus" />
        </button>
      </div>
    </el-card>

    <div class="dashboard-grid">
      <el-card shadow="never" class="panel-card status-panel">
        <template #header>
          <div class="panel-title">
            <div>
              <h2>{{ t("welcome.status.title") }}</h2>
              <p v-if="systemStatus">
                {{
                  t("welcome.status.checkedAt", {
                    time: dayjs(systemStatus.checked_at).format(
                      "YYYY-MM-DD HH:mm:ss"
                    )
                  })
                }}
              </p>
              <p v-else>{{ t("welcome.status.subtitle") }}</p>
            </div>
            <el-button
              circle
              :icon="Refresh"
              :loading="loading"
              :disabled="!canViewStatus"
              @click="refreshStatus()"
            />
          </div>
        </template>

        <el-empty
          v-if="!canViewStatus"
          :description="t('welcome.status.noPermission')"
          :image-size="72"
        />
        <el-skeleton v-else-if="loading && !systemStatus" :rows="5" animated />
        <div v-else-if="systemStatus" class="status-list">
          <div v-for="name in componentOrder" :key="name" class="status-row">
            <span
              class="status-dot"
              :class="systemStatus.components[name].status"
            />
            <div class="status-copy">
              <strong>{{ t(`welcome.status.components.${name}`) }}</strong>
              <small>
                {{
                  systemStatus.components[name].message ||
                  (systemStatus.components[name].latency_ms != null
                    ? `${systemStatus.components[name].latency_ms} ms`
                    : t("welcome.status.operational"))
                }}
              </small>
            </div>
            <el-tag
              :type="statusTagType(systemStatus.components[name].status)"
              size="small"
              effect="plain"
            >
              {{
                t(
                  `welcome.status.values.${systemStatus.components[name].status}`
                )
              }}
            </el-tag>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="panel-card resource-panel">
        <template #header>
          <div class="panel-title">
            <div>
              <h2>{{ t("welcome.resources.title") }}</h2>
              <p>{{ t("welcome.resources.subtitle") }}</p>
            </div>
            <Monitor class="panel-icon" />
          </div>
        </template>

        <el-skeleton v-if="loading && !systemStatus" :rows="5" animated />
        <el-empty
          v-else-if="!systemStatus"
          :description="t('welcome.resources.noData')"
          :image-size="72"
        />
        <div v-else class="resource-content">
          <div class="resource-primary">
            <div class="metric-ring">
              <el-progress
                type="dashboard"
                :percentage="systemStatus.resources.cpu.usage_percent"
                :status="
                  progressStatus(systemStatus.resources.cpu.usage_percent)
                "
                :width="116"
              />
              <strong>{{ t("welcome.resources.cpu") }}</strong>
              <small>
                {{ systemStatus.resources.cpu.physical_cores }} /
                {{ systemStatus.resources.cpu.logical_cores }}
                {{ t("welcome.resources.cores") }}
              </small>
            </div>
            <div class="metric-ring">
              <el-progress
                type="dashboard"
                :percentage="systemStatus.resources.memory.usage_percent"
                :status="
                  progressStatus(systemStatus.resources.memory.usage_percent)
                "
                :width="116"
              />
              <strong>{{ t("welcome.resources.memory") }}</strong>
              <small>
                {{ formatBytes(systemStatus.resources.memory.used_bytes) }} /
                {{ formatBytes(systemStatus.resources.memory.total_bytes) }}
              </small>
            </div>
          </div>

          <div class="resource-line">
            <div class="resource-label">
              <span><FolderOpened /> {{ t("welcome.resources.disk") }}</span>
              <strong>
                {{ formatBytes(systemStatus.resources.disk.used_bytes) }} /
                {{ formatBytes(systemStatus.resources.disk.total_bytes) }}
              </strong>
            </div>
            <el-progress
              :percentage="systemStatus.resources.disk.usage_percent"
              :status="
                progressStatus(systemStatus.resources.disk.usage_percent)
              "
              :stroke-width="10"
            />
          </div>

          <div class="gpu-section">
            <div class="resource-label">
              <span><Coin /> {{ t("welcome.resources.gpu") }}</span>
            </div>
            <div v-if="systemStatus.resources.gpu.available" class="gpu-list">
              <div
                v-for="gpu in systemStatus.resources.gpu.devices"
                :key="gpu.name"
                class="gpu-item"
              >
                <div>
                  <strong>{{ gpu.name }}</strong>
                  <small>
                    {{ gpu.temperature_celsius }}°C ·
                    {{ formatBytes(gpu.memory_used_bytes) }} /
                    {{ formatBytes(gpu.memory_total_bytes) }}
                  </small>
                </div>
                <el-progress
                  type="circle"
                  :percentage="gpu.usage_percent"
                  :width="62"
                  :stroke-width="7"
                />
              </div>
            </div>
            <div v-else class="gpu-unavailable">
              {{ t("welcome.resources.gpuUnavailable") }}
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped lang="scss">
.welcome-page {
  min-height: 100%;
  padding: 20px;
  background: var(--el-bg-color-page);
}

.hero-panel {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding: 28px 32px;
  margin-bottom: 18px;
  overflow: hidden;
  color: #fff;
  background:
    radial-gradient(circle at 85% 20%, rgb(255 255 255 / 18%), transparent 28%),
    linear-gradient(125deg, #173b68 0%, #245da5 55%, #2b7a78 120%);
  border-radius: 14px;
  box-shadow: 0 10px 28px rgb(21 62 105 / 16%);
}

.hero-eyebrow {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.18em;
  opacity: 0.68;
}

.hero-panel h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.25;
}

.hero-panel p {
  margin: 8px 0 0;
  font-size: 14px;
  opacity: 0.76;
}

.hero-meta {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  opacity: 0.9;
}

.panel-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
}

.panel-card :deep(.el-card__header) {
  padding: 18px 20px;
  border-bottom-color: var(--el-border-color-lighter);
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel-title h2 {
  margin: 0;
  font-size: 17px;
}

.panel-title p {
  margin: 5px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.panel-icon {
  width: 24px;
  height: 24px;
  color: var(--el-color-primary);
}

.quick-panel {
  margin-bottom: 18px;
}

.quick-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}

.quick-item {
  display: flex;
  gap: 12px;
  align-items: center;
  min-width: 0;
  padding: 16px;
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
  background: var(--el-fill-color-light);
  border: 1px solid transparent;
  border-radius: 10px;
  transition: all 0.2s ease;
}

.quick-item:hover {
  background: var(--el-bg-color);
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 6px 16px rgb(0 0 0 / 6%);
  transform: translateY(-2px);
}

.quick-item.disabled {
  cursor: not-allowed;
  opacity: 0.48;
  filter: grayscale(0.8);
  transform: none;
}

.quick-icon {
  display: grid;
  flex: 0 0 40px;
  place-items: center;
  width: 40px;
  height: 40px;
  font-size: 22px;
  background: currentcolor;
  border-radius: 10px;
}

.quick-icon :deep(svg) {
  color: #fff;
}

.quick-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.quick-copy strong,
.quick-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.quick-copy strong {
  font-size: 14px;
}

.quick-copy small {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.quick-plus {
  flex: 0 0 auto;
  width: 15px;
  color: var(--el-text-color-placeholder);
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(360px, 0.9fr) minmax(460px, 1.1fr);
  gap: 18px;
}

.status-list {
  display: grid;
  gap: 4px;
}

.status-row {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 11px 4px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}

.status-row:last-child {
  border-bottom: 0;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  box-shadow: 0 0 0 4px currentcolor;
  opacity: 0.75;
}

.status-dot.healthy {
  color: var(--el-color-success-light-5);
  background: var(--el-color-success);
}

.status-dot.degraded {
  color: var(--el-color-warning-light-5);
  background: var(--el-color-warning);
}

.status-dot.unhealthy {
  color: var(--el-color-danger-light-5);
  background: var(--el-color-danger);
}

.status-dot.not_configured {
  color: var(--el-color-info-light-5);
  background: var(--el-color-info);
}

.status-copy {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.status-copy strong {
  font-size: 14px;
}

.status-copy small {
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}

.resource-content {
  display: grid;
  gap: 22px;
}

.resource-primary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.metric-ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 12px;
}

.metric-ring strong {
  margin-top: -4px;
  font-size: 14px;
}

.metric-ring small {
  margin-top: 3px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.resource-line,
.gpu-section {
  padding: 0 4px;
}

.resource-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 9px;
  font-size: 13px;
}

.resource-label span {
  display: flex;
  gap: 7px;
  align-items: center;
  font-weight: 600;
}

.resource-label svg {
  width: 16px;
  color: var(--el-color-primary);
}

.resource-label strong {
  font-size: 11px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
}

.gpu-list {
  display: grid;
  gap: 8px;
}

.gpu-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 10px;
}

.gpu-item > div:first-child {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.gpu-item strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  white-space: nowrap;
}

.gpu-item small,
.gpu-unavailable {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.gpu-unavailable {
  padding: 16px;
  margin-top: 6px;
  text-align: center;
  background: var(--el-fill-color-lighter);
  border-radius: 10px;
}

@media (width <= 1280px) {
  .quick-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (width <= 900px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    align-items: flex-start;
  }

  .hero-meta {
    flex-direction: column;
    align-items: flex-end;
  }
}

@media (width <= 640px) {
  .welcome-page {
    padding: 12px;
  }

  .hero-panel {
    flex-direction: column;
    gap: 18px;
    padding: 22px;
  }

  .hero-meta {
    align-items: flex-start;
  }

  .quick-grid {
    grid-template-columns: 1fr;
  }
}
</style>
