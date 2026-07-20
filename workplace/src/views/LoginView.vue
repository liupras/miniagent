<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { AuthenticationError, useAuthStore } from "../stores/auth";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const formRef = ref<FormInstance>();
const loading = ref(false);
const form = reactive({ username: "", password: "" });
const rules = computed<FormRules>(() => ({
  username: [
    {
      required: true,
      message: t("login.validation.usernameRequired"),
      trigger: "blur",
    },
    {
      min: 3,
      max: 50,
      message: t("login.validation.usernameLength"),
      trigger: "blur",
    },
  ],
  password: [
    {
      required: true,
      message: t("login.validation.passwordRequired"),
      trigger: "blur",
    },
  ],
}));

function getLoginError(error: unknown) {
  if (error instanceof AuthenticationError) {
    if (error.code === "invalid_credentials") {
      return t("login.errors.invalidCredentials");
    }
    if (error.code === "account_locked") return t("login.errors.accountLocked");
  }
  return t("login.errors.generic");
}

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  loading.value = true;
  try {
    await auth.login(form.username.trim(), form.password);
    ElMessage.success(t("login.success"));
    const redirect =
      typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.replace(redirect);
  } catch (error) {
    ElMessage.error(getLoginError(error));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-brand" aria-label="MiniAgent Workplace">
      <div class="brand-mark">
        <img src="/logo.svg" alt="MiniAgent" />
      </div>
      <p class="eyebrow">{{ t("login.brandEyebrow") }}</p>
      <h1 v-html="t('login.brandTitle')" />
      <p class="brand-copy">{{ t("login.brandCopy") }}</p>
      <div class="brand-orbit orbit-one" />
      <div class="brand-orbit orbit-two" />
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="mobile-brand">
          <img src="/logo.svg" alt="MiniAgent" />
          <span>MiniAgent</span>
        </div>
        <p class="eyebrow">{{ t("login.eyebrow") }}</p>
        <h2>{{ t("login.title") }}</h2>
        <p class="login-tip">{{ t("login.tip") }}</p>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          @keyup.enter="submit"
        >
          <el-form-item :label="t('login.username')" prop="username">
            <el-input
              v-model="form.username"
              autocomplete="username"
              :placeholder="t('login.usernamePlaceholder')"
              clearable
            />
          </el-form-item>
          <el-form-item :label="t('login.password')" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              autocomplete="current-password"
              :placeholder="t('login.passwordPlaceholder')"
              show-password
            />
          </el-form-item>
          <el-button
            class="login-submit"
            type="primary"
            :loading="loading"
            @click="submit"
          >
            {{ t("login.submit") }}
          </el-button>
        </el-form>
      </div>
    </section>
  </main>
</template>
