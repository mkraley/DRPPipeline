/**
 * Listens for COLLECTOR_LINK_CLICK postMessage from iframes.
 *
 * When the user clicks a link in Source or Linked pane, the injected script
 * posts { type: "COLLECTOR_LINK_CLICK", url, referrer } to the parent.
 * We call loadLinked to fetch and display the new page without full reload.
 */
import { useEffect } from "react";
import { useCollectorStore } from "./store";

export function useLinkInterceptor() {
  const loadLinked = useCollectorStore((s) => s.loadLinked);

  useEffect(() => {
    const handler = (e: MessageEvent): void => {
      const d = e.data;
      if (d?.type === "COLLECTOR_LINK_CLICK" && typeof d.url === "string") {
        loadLinked(d.url, d.referrer ?? null, false);
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [loadLinked]);
}
