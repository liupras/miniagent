<script setup lang="ts">
import { useRouter } from "vue-router";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();

async function logout() {
  auth.logout();
  await router.replace({ name: "login" });
}
</script>

<template>
  <div class="home-page">
    <header class="home-header">
      <a class="home-logo" href="#/" aria-label="MiniAgent Workplace 首页">
        <img src="/logo.svg" alt="" />
        <span>MiniAgent</span>
        <small>Workplace</small>
      </a>
      <div class="user-actions">
        <el-avatar :src="auth.session?.avatar || undefined" :size="34">
          {{ auth.displayName.slice(0, 1).toUpperCase() }}
        </el-avatar>
        <span class="user-name">{{ auth.displayName }}</span>
        <el-button text @click="logout">退出登录</el-button>
      </div>
    </header>
    <main class="home-content" aria-label="工作台内容" />
  </div>
</template>
