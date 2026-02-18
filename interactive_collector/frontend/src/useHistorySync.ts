/**
 * Syncs app state to the URL via History API for shareable/bookmarkable links.
 *
 * Only drpid is stored in URL. sourceUrl and linkedUrl live in the store.
 * On popstate (back/forward), we restore drpid and let the store/load flow
 * determine source/linked state.
 */
import { useEffect } from "react";
import { useCollectorStore } from "./store";

/** Build URL search string from current state. */
function buildSearch(drpid: number | null): string {
  const params = new URLSearchParams();
  if (drpid != null) params.set("drpid", String(drpid));
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function useHistorySync() {
  const { drpid } = useCollectorStore();

  useEffect(() => {
    const search = buildSearch(drpid);
    const url = `${window.location.pathname}${search}`;
    if (window.location.search !== search) {
      window.history.replaceState({ drpid }, "", url);
    }
  }, [drpid]);

  // Handle back/forward - restore drpid; source/linked stay in store
  useEffect(() => {
    const handler = () => {
      const params = new URLSearchParams(window.location.search);
      const d = params.get("drpid");
      const drpidNum = d ? parseInt(d, 10) : null;
      if (drpidNum != null) {
        useCollectorStore.getState().loadProject(drpidNum);
      }
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, []);
}
