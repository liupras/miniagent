<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { Icon } from "@iconify/vue";
import { ElMessage, ElMessageBox } from "element-plus";
import MarkdownIt from "markdown-it";
import { useI18n } from "vue-i18n";
import { useRouter } from "vue-router";
import {
  deleteSession,
  getAvailableAgents,
  getMessages,
  getSessions,
  renameSession,
  streamAgentMessage,
} from "../api/chat";
import type { AppLocale } from "../i18n";
import { useAuthStore } from "../stores/auth";
import {
  themeOptions,
  usePreferencesStore,
  type ThemeTone,
} from "../stores/preferences";
import type { AgentSummary, ChatMessage, ChatSession } from "../types/chat";

const { t } = useI18n();
const router = useRouter();
const auth = useAuthStore();
const preferences = usePreferencesStore();
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });
const languageOptions: AppLocale[] = ["zh_CN", "en_US"];

const agents = ref<AgentSummary[]>([]);
const sessions = ref<ChatSession[]>([]);
const messages = ref<ChatMessage[]>([]);
const selectedAgentId = ref<number | null>(null);
const currentSessionId = ref<number | null>(null);
const searchText = ref("");
const prompt = ref("");
const version = ref("-");
const loadingSessions = ref(false);
const loadingMessages = ref(false);
const sending = ref(false);
const toolStatus = ref("");
const messageViewport = ref<HTMLElement | null>(null);
let searchTimer: number | undefined;
let streamController: AbortController | null = null;

const currentAgent = computed(() =>
  agents.value.find((agent) => agent.id === selectedAgentId.value),
);

function changeLanguage(event: Event) {
  preferences.setLanguage(
    (event.target as HTMLSelectElement).value as AppLocale,
  );
}

function changeTheme(theme: ThemeTone) {
  preferences.setTheme(theme);
}

async function logout() {
  streamController?.abort();
  auth.logout();
  await router.replace({ name: "login" });
}

async function loadSessions() {
  loadingSessions.value = true;
  try {
    sessions.value = (await getSessions(searchText.value.trim())).items;
  } catch {
    ElMessage.error(t("chat.errors.loadSessions"));
  } finally {
    loadingSessions.value = false;
  }
}

async function initializeWorkspace() {
  try {
    const [agentData] = await Promise.all([
      getAvailableAgents(),
      loadSessions(),
    ]);
    agents.value = agentData.items;
    version.value = agentData.version;
    if (!selectedAgentId.value && agents.value.length) {
      selectedAgentId.value = agents.value[0].id;
    }
  } catch {
    ElMessage.error(t("chat.errors.loadAgents"));
  }
}

async function selectSession(session: ChatSession) {
  if (sending.value || currentSessionId.value === session.session_id) return;
  currentSessionId.value = session.session_id;
  if (
    session.agent_id &&
    agents.value.some((agent) => agent.id === session.agent_id)
  ) {
    selectedAgentId.value = session.agent_id;
  }
  loadingMessages.value = true;
  messages.value = [];
  try {
    messages.value = (await getMessages(session.session_id)).items;
    await scrollToBottom();
  } catch {
    ElMessage.error(t("chat.errors.loadMessages"));
  } finally {
    loadingMessages.value = false;
  }
}

function startNewChat() {
  if (sending.value) return;
  currentSessionId.value = null;
  messages.value = [];
  prompt.value = "";
  toolStatus.value = "";
}

async function editSession(session: ChatSession) {
  try {
    const result = await ElMessageBox.prompt(
      t("sessions.renameMessage"),
      t("sessions.rename"),
      {
        inputValue: session.title || t("sessions.untitled"),
        inputPattern: /\S+/,
        inputErrorMessage: t("sessions.titleRequired"),
        confirmButtonText: t("common.confirm"),
        cancelButtonText: t("common.cancel"),
      },
    );
    await renameSession(session.session_id, result.value.trim());
    session.title = result.value.trim();
    ElMessage.success(t("sessions.renamed"));
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(t("sessions.renameFailed"));
    }
  }
}

async function removeSession(session: ChatSession) {
  try {
    await ElMessageBox.confirm(
      t("sessions.deleteMessage", {
        title: session.title || t("sessions.untitled"),
      }),
      t("sessions.delete"),
      {
        type: "warning",
        confirmButtonText: t("common.delete"),
        cancelButtonText: t("common.cancel"),
      },
    );
    await deleteSession(session.session_id);
    if (currentSessionId.value === session.session_id) startNewChat();
    await loadSessions();
    ElMessage.success(t("sessions.deleted"));
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(t("sessions.deleteFailed"));
    }
  }
}

function renderMessage(content: string) {
  return markdown.render(content);
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(
    preferences.language === "zh_CN" ? "zh-CN" : "en-US",
    { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" },
  ).format(date);
}

async function scrollToBottom() {
  await nextTick();
  if (messageViewport.value) {
    messageViewport.value.scrollTop = messageViewport.value.scrollHeight;
  }
}

async function sendMessage() {
  const query = prompt.value.trim();
  if (!query || !selectedAgentId.value || sending.value) return;

  prompt.value = "";
  toolStatus.value = "";
  const userMessage: ChatMessage = {
    id: `user-${Date.now()}`,
    role: "user",
    content: query,
  };
  const assistantMessage: ChatMessage = {
    id: `assistant-${Date.now()}`,
    role: "assistant",
    content: "",
    streaming: true,
  };
  messages.value.push(userMessage, assistantMessage);
  sending.value = true;
  streamController = new AbortController();
  await scrollToBottom();

  try {
    await streamAgentMessage({
      agentId: selectedAgentId.value,
      query,
      sessionId: currentSessionId.value,
      signal: streamController.signal,
      onEvent(event) {
        if (event.event === "session" && event.session_id) {
          currentSessionId.value = event.session_id;
        } else if (event.event === "text" && event.chunk) {
          assistantMessage.content += event.chunk;
          void scrollToBottom();
        } else if (event.event === "tool_start" && event.tools?.length) {
          toolStatus.value = t("chat.usingTools", {
            tools: event.tools.join(", "),
          });
        } else if (event.event === "error") {
          throw new Error(event.message || "stream error");
        }
      },
    });
    if (!assistantMessage.content) {
      assistantMessage.content = t("chat.emptyResponse");
    }
  } catch (error) {
    if ((error as Error).name === "AbortError") {
      if (!assistantMessage.content)
        assistantMessage.content = t("chat.stopped");
    } else {
      assistantMessage.content ||= t("chat.errors.send");
      ElMessage.error(t("chat.errors.send"));
    }
  } finally {
    assistantMessage.streaming = false;
    sending.value = false;
    toolStatus.value = "";
    streamController = null;
    await loadSessions();
    await scrollToBottom();
  }
}

function stopStreaming() {
  streamController?.abort();
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    void sendMessage();
  }
}

watch(searchText, () => {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(() => void loadSessions(), 250);
});

onMounted(initializeWorkspace);
onBeforeUnmount(() => {
  if (searchTimer) window.clearTimeout(searchTimer);
  streamController?.abort();
});
</script>

<template>
  <div class="home-page">
    <header class="home-header">
      <a class="home-logo" href="#/" :aria-label="t('home.logoLabel')">
        <img src="/logo.svg" alt="" />
        <span>MiniAgent</span>
        <small>Workplace</small>
        <em>v{{ version }}</em>
      </a>

      <div class="header-tools">
        <label class="language-control">
          <span>{{ t("common.language") }}</span>
          <select :value="preferences.language" @change="changeLanguage">
            <option
              v-for="locale in languageOptions"
              :key="locale"
              :value="locale"
            >
              {{ t(`languages.${locale}`) }}
            </option>
          </select>
        </label>

        <div class="theme-control" :aria-label="t('common.theme')">
          <span>{{ t("common.theme") }}</span>
          <div class="theme-options">
            <button
              v-for="option in themeOptions"
              :key="option.value"
              type="button"
              class="theme-swatch"
              :class="{ active: preferences.theme === option.value }"
              :style="{ '--swatch-color': option.color }"
              :title="t(`themes.${option.value}`)"
              :aria-label="t(`themes.${option.value}`)"
              :aria-pressed="preferences.theme === option.value"
              @click="changeTheme(option.value)"
            />
          </div>
        </div>

        <div class="user-actions">
          <el-avatar :src="auth.session?.avatar || undefined" :size="34">
            {{ auth.displayName.slice(0, 1).toUpperCase() }}
          </el-avatar>
          <span class="user-name">{{ auth.displayName }}</span>
          <el-button text @click="logout">{{ t("common.logout") }}</el-button>
        </div>
      </div>
    </header>

    <main class="workspace-shell" :aria-label="t('home.contentLabel')">
      <aside class="session-sidebar">
        <div class="sidebar-heading">
          <div>
            <span class="section-eyebrow">{{ t("sessions.eyebrow") }}</span>
            <h2>{{ t("sessions.title") }}</h2>
          </div>
          <el-button
            circle
            type="primary"
            :title="t('sessions.new')"
            :aria-label="t('sessions.new')"
            :disabled="sending"
            @click="startNewChat"
          >
            <Icon icon="lucide:plus" width="18" />
          </el-button>
        </div>

        <el-input
          v-model="searchText"
          clearable
          :placeholder="t('sessions.search')"
          class="session-search"
        >
          <template #prefix><Icon icon="lucide:search" /></template>
        </el-input>

        <div v-loading="loadingSessions" class="session-list">
          <div
            v-for="session in sessions"
            :key="session.session_id"
            role="button"
            tabindex="0"
            class="session-item"
            :class="{ active: currentSessionId === session.session_id }"
            @click="selectSession(session)"
            @keydown.enter="selectSession(session)"
          >
            <span class="session-icon"
              ><Icon icon="lucide:message-square"
            /></span>
            <span class="session-copy">
              <strong>{{ session.title || t("sessions.untitled") }}</strong>
              <small>
                {{ session.agent_name || t("sessions.unknownAgent") }} ·
                {{ formatTime(session.updated_at) }}
              </small>
            </span>
            <span class="session-actions">
              <button
                type="button"
                :title="t('sessions.rename')"
                :aria-label="t('sessions.rename')"
                @click.stop="editSession(session)"
              >
                <Icon icon="lucide:pencil" />
              </button>
              <button
                type="button"
                :title="t('sessions.delete')"
                :aria-label="t('sessions.delete')"
                @click.stop="removeSession(session)"
              >
                <Icon icon="lucide:trash-2" />
              </button>
            </span>
          </div>
          <div
            v-if="!loadingSessions && !sessions.length"
            class="sidebar-empty"
          >
            <Icon icon="lucide:messages-square" width="28" />
            <span>{{ t("sessions.empty") }}</span>
          </div>
        </div>
      </aside>

      <section class="chat-panel">
        <div class="chat-toolbar">
          <div class="agent-heading">
            <span class="agent-avatar"><Icon icon="lucide:bot" /></span>
            <div>
              <label for="agent-select">{{ t("agents.select") }}</label>
              <select
                id="agent-select"
                v-model="selectedAgentId"
                :disabled="sending || !agents.length"
                @change="startNewChat"
              >
                <option v-if="!agents.length" :value="null">
                  {{ t("agents.empty") }}
                </option>
                <option
                  v-for="agent in agents"
                  :key="agent.id"
                  :value="agent.id"
                >
                  {{ agent.name }}
                </option>
              </select>
            </div>
          </div>
          <p v-if="currentAgent?.description">{{ currentAgent.description }}</p>
          <el-button :disabled="sending" @click="startNewChat">
            <Icon icon="lucide:square-pen" />
            {{ t("sessions.new") }}
          </el-button>
        </div>

        <div ref="messageViewport" class="message-viewport">
          <div v-if="loadingMessages" class="chat-state">
            <Icon icon="lucide:loader-circle" class="spin" width="28" />
            <span>{{ t("chat.loading") }}</span>
          </div>
          <div v-else-if="!messages.length" class="welcome-state">
            <span class="welcome-icon"><Icon icon="lucide:sparkles" /></span>
            <h1>{{ t("chat.welcome", { name: auth.displayName }) }}</h1>
            <p v-if="agents.length">{{ t("chat.welcomeTip") }}</p>
            <p v-else>{{ t("agents.emptyTip") }}</p>
          </div>
          <div v-else class="message-list">
            <article
              v-for="message in messages"
              :key="message.id"
              class="message-row"
              :class="`message-${message.role}`"
            >
              <div class="message-avatar">
                <Icon
                  :icon="message.role === 'user' ? 'lucide:user' : 'lucide:bot'"
                />
              </div>
              <div class="message-body">
                <strong>{{
                  message.role === "user"
                    ? auth.displayName
                    : currentAgent?.name || "MiniAgent"
                }}</strong>
                <div
                  class="markdown-body"
                  v-html="renderMessage(message.content)"
                />
                <span v-if="message.streaming" class="typing-cursor" />
              </div>
            </article>
          </div>
        </div>

        <div class="composer-wrap">
          <div v-if="toolStatus" class="tool-status">
            <Icon icon="lucide:wrench" /> {{ toolStatus }}
          </div>
          <div class="composer" :class="{ disabled: !agents.length }">
            <textarea
              v-model="prompt"
              rows="1"
              :disabled="!agents.length || sending"
              :placeholder="
                agents.length ? t('chat.placeholder') : t('agents.empty')
              "
              @keydown="handleComposerKeydown"
            />
            <button
              v-if="sending"
              type="button"
              class="send-button stop-button"
              :aria-label="t('chat.stop')"
              :title="t('chat.stop')"
              @click="stopStreaming"
            >
              <Icon icon="lucide:square" />
            </button>
            <button
              v-else
              type="button"
              class="send-button"
              :disabled="!prompt.trim() || !selectedAgentId"
              :aria-label="t('chat.send')"
              :title="t('chat.send')"
              @click="sendMessage"
            >
              <Icon icon="lucide:arrow-up" />
            </button>
          </div>
          <small>{{ t("chat.keyboardTip") }}</small>
        </div>
      </section>
    </main>
  </div>
</template>
