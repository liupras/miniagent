import { createApp } from "vue";
import { createPinia } from "pinia";
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";
import App from "./App.vue";
import { i18n } from "./i18n";
import router from "./router";
import { useAuthStore } from "./stores/auth";
import { usePreferencesStore } from "./stores/preferences";
import "./style.css";

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
useAuthStore(pinia).initialize();
usePreferencesStore(pinia).initialize();
app.use(i18n).use(router).use(ElementPlus).mount("#app");
