/**
 * Zustand store for Interactive Collector state.
 *
 * Holds: drpid, sourceUrl, scoreboard, metadata, folderPath.
 * Collector does not display source/linked panes; user uses Copy & Open
 * to browse in separate window with extension.
 */
import { create } from "zustand";

export interface ScoreboardNode {
  url: string;
  referrer: string | null;
  status_label: string;
  is_dupe: boolean;
  idx: number;
  children: ScoreboardNode[];
  is_download?: boolean;
  filename?: string;
  extension?: string;
  title?: string;
}

export interface Metadata {
  title: string;
  summary: string;
  keywords: string;
  agency: string;
  office: string;
  time_start: string;
  time_end: string;
  download_date: string;
}

interface CollectorState {
  drpid: number | null;
  sourceUrl: string;
  scoreboard: ScoreboardNode[];
  scoreboardUrls: string[];
  metadata: Metadata;
  folderPath: string | null;
  loading: boolean;
  error: string | null;
  saveProgress: string;
  saveModalOpen: boolean;
  noLinksModalOpen: boolean;
  skipModalOpen: boolean;
  downloadsWatcherActive: boolean;
}

interface CollectorActions {
  setDrpid: (v: number | null) => void;
  setMetadata: (m: Partial<Metadata>) => void;
  save: () => Promise<void>;
  closeSaveModal: () => void;
  loadProject: (drpid: number) => Promise<void>;
  loadFirstProject: () => Promise<void>;
  loadNext: () => Promise<void>;
  refreshScoreboard: () => Promise<void>;
  setNoLinks: () => Promise<void>;
  closeNoLinksModal: () => void;
  openSkipModal: () => void;
  closeSkipModal: () => void;
  skip: (reason: string) => Promise<void>;
  startDownloadsWatcher: () => Promise<void>;
  stopDownloadsWatcher: () => Promise<void>;
}

const API = "/api";

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

function applyLoadResult(
  data: {
    DRPID: number;
    source_url?: string;
    folder_path?: string | null;
    scoreboard?: ScoreboardNode[];
    scoreboard_urls?: string[];
    metadata?: Partial<Metadata>;
  },
  set: (partial: Partial<CollectorState>) => void
) {
  const meta = data.metadata ?? {};
  set({
    drpid: data.DRPID,
    sourceUrl: (data.source_url || "").trim(),
    folderPath: (data.folder_path || "").trim() || null,
    scoreboard: Array.isArray(data.scoreboard) ? data.scoreboard : [],
    scoreboardUrls: Array.isArray(data.scoreboard_urls) ? data.scoreboard_urls : [],
    metadata: {
      title: String(meta.title ?? ""),
      summary: String(meta.summary ?? ""),
      keywords: String(meta.keywords ?? ""),
      agency: String(meta.agency ?? ""),
      office: String(meta.office ?? ""),
      time_start: String(meta.time_start ?? ""),
      time_end: String(meta.time_end ?? ""),
      download_date: String(meta.download_date ?? ""),
    },
    loading: false,
    error: null,
  });
}

export const useCollectorStore = create<CollectorState & CollectorActions>((set, get) => ({
  drpid: null,
  sourceUrl: "",
  scoreboard: [],
  scoreboardUrls: [],
  metadata: {
    title: "",
    summary: "",
    keywords: "",
    agency: "",
    office: "",
    time_start: "",
    time_end: "",
    download_date: "",
  },
  folderPath: null,
  loading: false,
  error: null,
  saveProgress: "",
  saveModalOpen: false,
  noLinksModalOpen: false,
  skipModalOpen: false,
  downloadsWatcherActive: false,

  setDrpid: (v) => set({ drpid: v }),

  setMetadata: (m) =>
    set((s) => ({ metadata: { ...s.metadata, ...m } })),

  save: async () => {
    const { drpid, folderPath, metadata } = get();
    if (!drpid) return;
    set({ saveProgress: "Saving...", saveModalOpen: true });
    const form = new FormData();
    form.append("drpid", String(drpid));
    form.append("folder_path", folderPath || "");
    form.append("scoreboard_urls_json", JSON.stringify(get().scoreboardUrls));
    form.append("metadata_title", metadata.title);
    form.append("metadata_summary", metadata.summary);
    form.append("metadata_keywords", metadata.keywords);
    form.append("metadata_agency", metadata.agency);
    form.append("metadata_office", metadata.office);
    form.append("metadata_time_start", metadata.time_start);
    form.append("metadata_time_end", metadata.time_end);
    form.append("metadata_download_date", metadata.download_date);
    // Save only updates DB (no PDF conversion) and stops downloads watcher
    try {
      const res = await fetch(`${API}/save`, { method: "POST", body: form });
      if (!res.ok) {
        set({ saveProgress: `Error: ${await res.text()}`, saveModalOpen: true });
        return;
      }
      if (res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (line.startsWith("DONE\t")) {
              set({ saveProgress: "Saved.", saveModalOpen: true });
              break;
            }
            if (line.startsWith("ERROR\t")) {
              set({ saveProgress: `Error: ${line.split("\t")[1] ?? "unknown"}`, saveModalOpen: true });
              break;
            }
          }
        }
      } else {
        set({ saveProgress: "Saved.", saveModalOpen: true });
      }
      await get().stopDownloadsWatcher();
    } catch (e) {
      set({
        saveProgress: `Error: ${e instanceof Error ? e.message : "Failed"}`,
        saveModalOpen: true,
      });
    }
  },

  closeSaveModal: () => set({ saveModalOpen: false }),

  refreshScoreboard: async () => {
    try {
      const data = await fetchJson<{ scoreboard: ScoreboardNode[]; urls: string[] }>(
        `${API}/scoreboard`
      );
      set({ scoreboard: data.scoreboard, scoreboardUrls: data.urls });
    } catch {
      // ignore
    }
  },

  setNoLinks: async () => {
    const { drpid } = get();
    if (!drpid) return;
    try {
      await fetchJson<{ ok: boolean }>(`${API}/no-links`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ drpid }),
      });
      set({ noLinksModalOpen: true });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "Failed to set no links" });
    }
  },

  closeNoLinksModal: () => set({ noLinksModalOpen: false }),

  openSkipModal: () => set({ skipModalOpen: true }),
  closeSkipModal: () => set({ skipModalOpen: false }),

  skip: async (reason) => {
    const { drpid, folderPath, metadata } = get();
    if (!drpid) return;
    const body = {
      drpid,
      reason: reason.trim(),
      folder_path: folderPath || "",
      metadata_title: metadata.title,
      metadata_summary: metadata.summary,
      metadata_keywords: metadata.keywords,
      metadata_agency: metadata.agency,
      metadata_office: metadata.office,
      metadata_time_start: metadata.time_start,
      metadata_time_end: metadata.time_end,
      metadata_download_date: metadata.download_date,
    };
    try {
      const data = await fetchJson<{ ok: boolean; error?: string }>(`${API}/skip`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (data.ok) {
        set({ skipModalOpen: false });
        await get().stopDownloadsWatcher();
      } else {
        throw new Error(data.error || "Skip failed");
      }
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "Skip failed" });
    }
  },

  startDownloadsWatcher: async () => {
    const { drpid } = get();
    if (!drpid) return;
    const res = await fetch(`${API}/downloads-watcher/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ drpid }),
    });
    const data = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string };
    if (res.ok && data.ok) {
      set({ downloadsWatcherActive: true });
      return;
    }
    throw new Error(data.error || `Watcher could not start (${res.status})`);
  },

  stopDownloadsWatcher: async () => {
    try {
      const data = await fetchJson<{ ok: boolean }>(`${API}/downloads-watcher/stop`, {
        method: "POST",
      });
      set({ downloadsWatcherActive: false });
      if (data.ok) await get().refreshScoreboard();
    } catch {
      set({ downloadsWatcherActive: false });
    }
  },

  loadProject: async (drpid) => {
    set({ loading: true, error: null });
    if (get().downloadsWatcherActive) {
      await get().stopDownloadsWatcher();
    }
    try {
      const data = await fetchJson<{
        DRPID: number;
        source_url?: string;
        folder_path?: string | null;
        scoreboard?: ScoreboardNode[];
        scoreboard_urls?: string[];
        metadata?: Partial<Metadata>;
      }>(`${API}/projects/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ drpid }),
      });
      applyLoadResult(data, set);
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : "Failed to load",
      });
    }
  },

  loadFirstProject: async () => {
    set({ loading: true, error: null });
    if (get().downloadsWatcherActive) {
      await get().stopDownloadsWatcher();
    }
    try {
      const data = await fetchJson<{
        DRPID: number;
        source_url?: string;
        folder_path?: string | null;
        scoreboard?: ScoreboardNode[];
        scoreboard_urls?: string[];
        metadata?: Partial<Metadata>;
      }>(`${API}/projects/load`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      applyLoadResult(data, set);
    } catch {
      set({ loading: false });
      // No eligible project - leave state empty
    }
  },

  loadNext: async () => {
    const { drpid } = get();
    if (!drpid) return;
    try {
      const proj = await fetchJson<{ source_url?: string; DRPID?: number }>(
        `${API}/projects/next?current_drpid=${drpid}`
      );
      if (proj.source_url && proj.DRPID) {
        await get().loadProject(proj.DRPID);
      }
    } catch {
      // No next project
    }
  },
}));
