import { createRouter, createWebHashHistory } from "vue-router";
import { getSession } from "../utils/session";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("../views/LoginView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/",
      name: "home",
      component: () => import("../views/HomeView.vue"),
      meta: { requiresAuth: true },
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

router.beforeEach((to) => {
  const authenticated = Boolean(getSession()?.accessToken);
  if (to.meta.requiresAuth && !authenticated) {
    return { name: "login", query: { redirect: to.fullPath } };
  }
  if (to.meta.guestOnly && authenticated) return { name: "home" };
  return true;
});

export default router;
