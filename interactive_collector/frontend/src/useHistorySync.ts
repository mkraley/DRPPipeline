/**
 * Syncs app state to the URL via History API for shareable/bookmarkable links.
 *
 * When sourceUrl or linkedUrl changes, we pushState with query params.
 * On popstate (back/forward), we parse the URL and restore state.
 */
import { useEffect } from "react";
import { useCollectorStore } from "./store";

/** Build URL search string from current state. */
function buildSearch(drpid: number | null, sourceUrl: string, linkedUrl: string): string {
  const params = new URLSearchParams();
  if (drpid != null) params.set("drpid", String(drpid));
  if (sourceUrl) params.set("source", sourceUrl);
  if (linkedUrl) params.set("linked", linkedUrl);
  const s = params.toString();
  return s ? `?${s}` : "";
}

export function useHistorySync() {
  const { drpid, sourceUrl, linkedUrl, loadSource, loadLinked } = useCollectorStore();

  // Push state when key fields change
  useEffect(() => {
    const search = buildSearch(drpid, sourceUrl, linkedUrl);
    const url = `${window.location.pathname}${search}`;
    if (window.location.search !== search) {
      window.history.replaceState({ drpid, sourceUrl, linkedUrl }, "", url);
    }
  }, [drpid, sourceUrl, linkedUrl]);

  // Handle back/forward - refetch from URL
  useEffect(() => {
    const handler = async () => {
      const params = new URLSearchParams(window.location.search);
      const d = params.get("drpid");
      const src = params.get("source");
      const lnk = params.get("linked");
      const drpidNum = d ? parseInt(d, 10) : null;
      if (src) {
        await loadSource(src, drpidNum);
        if (lnk) loadLinked(lnk, src, false);
      }
    };
    window.addEventListener("popstate", handler);
    return () => window.removeEventListener("popstate", handler);
  }, [loadSource, loadLinked]);
}
