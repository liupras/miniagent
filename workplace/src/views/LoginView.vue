<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, type FormInstance, type FormRules } from "element-plus";
import { useAuthStore } from "../stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const formRef = ref<FormInstance>();
const loading = ref(false);
const form = reactive({ username: "", password: "" });
const rules: FormRules = {
  username: [
    { required: true, message: "请输入账号", trigger: "blur" },
    { min: 3, max: 50, message: "账号长度为 3–50 个字符", trigger: "blur" },
  ],
  password: [{ required: true, message: "请输入密码", trigger: "blur" }],
};

async function submit() {
  const valid = await formRef.value?.validate().catch(() => false);
  if (!valid) return;
  loading.value = true;
  try {
    await auth.login(form.username.trim(), form.password);
    ElMessage.success("登录成功");
    const redirect =
      typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.replace(redirect);
  } catch (error) {
    ElMessage.error(
      error instanceof Error ? error.message : "登录失败，请稍后重试",
    );
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
      <p class="eyebrow">MINIAGENT WORKPLACE</p>
      <h1>让智能体成为你的<br />日常工作伙伴</h1>
      <p class="brand-copy">登录后即可使用为你配置的智能体能力。</p>
      <div class="brand-orbit orbit-one" />
      <div class="brand-orbit orbit-two" />
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="mobile-brand">
          <img src="/logo.svg" alt="MiniAgent" />
          <span>MiniAgent</span>
        </div>
        <p class="eyebrow">WELCOME BACK</p>
        <h2>登录工作台</h2>
        <p class="login-tip">请输入你的账号和密码继续</p>

        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          size="large"
          @keyup.enter="submit"
        >
          <el-form-item label="账号" prop="username">
            <el-input
              v-model="form.username"
              autocomplete="username"
              placeholder="请输入账号"
              clearable
            />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              autocomplete="current-password"
              placeholder="请输入密码"
              show-password
            />
          </el-form-item>
          <el-button
            class="login-submit"
            type="primary"
            :loading="loading"
            @click="submit"
          >
            登录
          </el-button>
        </el-form>
      </div>
    </section>
  </main>
</template>
