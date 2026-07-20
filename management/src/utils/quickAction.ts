import { nextTick, watch } from "vue";
import { useRoute } from "vue-router";

function cleanQuickActionFromAddress() {
  const url = new URL(window.location.href);
  const [hashPath, hashQuery = ""] = url.hash.slice(1).split("?");
  const query = new URLSearchParams(hashQuery);
  query.delete("quickAction");
  query.delete("quickActionId");
  url.hash = `${hashPath}${query.size ? `?${query.toString()}` : ""}`;
  window.history.replaceState(window.history.state, "", url);
}

/** Consume a one-shot action passed by the home-page shortcut. */
export function useQuickAction(actionName: string, callback: () => void) {
  const route = useRoute();

  watch(
    () => [route.query.quickAction, route.query.quickActionId] as const,
    async ([value]) => {
      if (value !== actionName) return;
      await nextTick();
      callback();
      // Updating Vue Router here remounts keep-alive views because PureAdmin
      // keys them by fullPath, which immediately closes the dialog we opened.
      cleanQuickActionFromAddress();
    },
    { immediate: true }
  );
}
