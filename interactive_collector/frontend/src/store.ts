/**
 * Zustand store for Interactive Collector state.
 *
 * Holds: drpid, sourceUrl, linkedUrl, referrer, scoreboard, metadata,
 * folderPath. Actions call the backend API.
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
  linkedUrl: string;
  referrer: string | null;
  sourceSrcdoc: string | null;
  linkedSrcdoc: string | null;
  sourceMessage: string | null;
  linkedMessage: string | null;
  scoreboard: ScoreboardNode[];
  scoreboardUrls: string[];
  metadata: Metadata;
  folderPath: string | null;
  checkedIndices: Set<number>;
  loading: boolean;
  error: string | null;
  saveProgress: string;
  saveModalOpen: boolean;
  linkedIsBinary: boolean;
  linkedBinaryUrl: string | null;
  linkedBinaryReferrer: string | null;
  downloadProgress: string;
  downloadModalOpen: boolean;
  noLinksModalOpen: boolean;
  downloadsWatcherActive: boolean;
}

interface CollectorActions {
  setDrpid: (v: number | null) => void;
  loadSource: (url: string, drpid?: number | null) => Promise<void>;
  loadLinked: (url: string, referrer: string | null, fromScoreboard?: boolean) => Promise<void>;
  setChecked: (idx: number, checked: boolean) => void;
  setMetadata: (m: Partial<Metadata>) => void;
  save: () => Promise<void>;
  closeSaveModal: () => void;
  loadProject: (drpid: number) => Promise<void>;
  loadFirstProject: () => Promise<void>;
  loadNext: () => Promise<void>;
  downloadBinary: () => Promise<void>;
  closeDownloadModal: () => void;
  refreshScoreboard: () => Promise<void>;
  clearScoreboard: () => Promise<void>;
  setNoLinks: () => Promise<void>;
  closeNoLinksModal: () => void;
  startDownloadsWatcher: () => Promise<void>;
  stopDownloadsWatcher: () => Promise<void>;
}

const API = "/api";

function walkScoreboard(nodes: ScoreboardNode[]): ScoreboardNode[] {
  const flat: ScoreboardNode[] = [];
  function walk(n: ScoreboardNode[]) {
    for (const node of n) {
      flat.push(node);
      if (node.children?.length) walk(node.children);
    }
  }
  walk(nodes);
  return flat;
}

/** Compute default-checked indices: original source + OK, or OK non-dupes. */
function defaultCheckedIndices(scoreboard: ScoreboardNode[], originalSourceUrl: string): Set<number> {
  const set = new Set<number>();
  for (const n of walkScoreboard(scoreboard)) {
    if (n.is_download) continue;
    const isOk = n.status_label.includes("OK");
    const baseChecked = (n.url === originalSourceUrl && isOk) || (isOk && !n.is_dupe);
    if (baseChecked) set.add(n.idx);
  }
  return set;
}

/** Merge checkedIndices: preserve user choices for existing nodes, add defaults for new nodes only. */
function mergeCheckedIndices(
  prevChecked: Set<number>,
  prevScoreboard: ScoreboardNode[],
  nextScoreboard: ScoreboardNode[],
  sourceUrl: string
): Set<number> {
  const prevIndices = new Set(walkScoreboard(prevScoreboard).map((n) => n.idx));
  const nextIndices = new Set(walkScoreboard(nextScoreboard).map((n) => n.idx));
  const defaults = defaultCheckedIndices(nextScoreboard, sourceUrl);
  const merged = new Set<number>();
  for (const idx of nextIndices) {
    if (prevIndices.has(idx)) {
      if (prevChecked.has(idx)) merged.add(idx);
    } else if (defaults.has(idx)) {
      merged.add(idx);
    }
  }
  return merged;
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `HTTP ${res.status}`);
  }
  return res.json();
}

export const useCollectorStore = create<CollectorState & CollectorActions>((set, get) => ({
  drpid: null,
  sourceUrl: "",
  linkedUrl: "",
  referrer: null,
  sourceSrcdoc: null,
  linkedSrcdoc: null,
  sourceMessage: null,
  linkedMessage: null,
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
  checkedIndices: new Set<number>(),
  loading: false,
  error: null,
  saveProgress: "",
  saveModalOpen: false,
  linkedIsBinary: false,
  linkedBinaryUrl: null,
  linkedBinaryReferrer: null,
  downloadProgress: "",
  downloadModalOpen: false,
  noLinksModalOpen: false,
  downloadsWatcherActive: false,

  setDrpid: (v) => set({ drpid: v }),

  setChecked: (idx, checked) =>
    set((s) => {
      const next = new Set(s.checkedIndices);
      if (checked) next.add(idx);
      else next.delete(idx);
      return { checkedIndices: next };
    }),

  setMetadata: (m) =>
    set((s) => ({ metadata: { ...s.metadata, ...m } })),

  loadSource: async (url, drpid) => {
    set({ loading: true, error: null });
    try {
      const data = await fetchJson<{
        srcdoc: string | null;
        body_message: string | null;
        status_label: string;
        h1_text: string;
        extracted_title?: string;
        extracted_agency?: string;
        extracted_office?: string;
        extracted_keywords?: string;
        scoreboard: ScoreboardNode[];
        scoreboard_urls: string[];
        folder_path: string | null;
      }>(`${API}/load-source`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, drpid: drpid ?? null }),
      });
      const checked = defaultCheckedIndices(data.scoreboard, url);
      const pid = drpid ?? get().drpid;
      // Load project metadata if we have drpid
      let meta = get().metadata;
      if (pid) {
        try {
          const proj = await fetchJson<Record<string, unknown>>(`${API}/projects/${pid}`);
          meta = {
            title: String(proj.title ?? ""),
            summary: String(proj.summary ?? ""),
            keywords: String(proj.keywords ?? ""),
            agency: String(proj.agency ?? ""),
            office: String(proj.office ?? ""),
            time_start: String(proj.time_start ?? ""),
            time_end: String(proj.time_end ?? ""),
            download_date: String(proj.download_date ?? ""),
          };
          if (!meta.title) meta.title = data.extracted_title || data.h1_text || "";
          if (!meta.agency) meta.agency = data.extracted_agency || "";
          if (!meta.office) meta.office = data.extracted_office || "";
          if (!meta.keywords) meta.keywords = data.extracted_keywords || "";
          if (!meta.download_date) meta.download_date = new Date().toISOString().slice(0, 10);
        } catch {
          meta = { ...meta, title: data.extracted_title || data.h1_text || "" };
          if (!meta.agency) meta.agency = data.extracted_agency || "";
          if (!meta.office) meta.office = data.extracted_office || "";
          if (!meta.keywords) meta.keywords = data.extracted_keywords || "";
          if (!meta.download_date) meta.download_date = new Date().toISOString().slice(0, 10);
        }
      }
      set({
        sourceUrl: url,
        linkedUrl: "",
        referrer: null,
        sourceSrcdoc: data.srcdoc,
        sourceMessage: data.body_message,
        linkedSrcdoc: null,
        linkedMessage: null,
        linkedIsBinary: false,
        linkedBinaryUrl: null,
        linkedBinaryReferrer: null,
        scoreboard: data.scoreboard,
        scoreboardUrls: data.scoreboard_urls,
        folderPath: data.folder_path,
        drpid: pid,
        checkedIndices: checked,
        metadata: meta,
        loading: false,
        error: null,
      });
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : "Failed to load",
      });
    }
  },

  loadLinked: async (url, referrer, fromScoreboard) => {
    const { sourceUrl, drpid } = get();
    const effectiveSourceUrl = sourceUrl || url;
    const looksLikeBinary = /\.(pdf|zip|csv|xlsx?|docx?|pptx?|json|xml|rss)(\?|$)/i.test(url);
    set({
      loading: true,
      error: null,
      ...(looksLikeBinary ? { downloadModalOpen: true, downloadProgress: "Preparing download..." } : {}),
    });
    try {
      const data = await fetchJson<{
        srcdoc: string | null;
        status_label: string;
        linked_display_url: string;
        body_message: string | null;
        scoreboard: ScoreboardNode[];
        scoreboard_urls: string[];
        is_binary?: boolean;
        linked_binary_url?: string | null;
        folder_path?: string | null;
      }>(`${API}/load-page`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          referrer,
          source_url: effectiveSourceUrl,
          drpid,
          from_scoreboard: fromScoreboard,
        }),
      });
      const isBinary = Boolean(data.is_binary && data.linked_binary_url);
      const nextScoreboard = Array.isArray(data.scoreboard) ? [...data.scoreboard] : data.scoreboard ?? [];
      const prev = get();
      const checked = fromScoreboard
        ? prev.checkedIndices
        : mergeCheckedIndices(
            prev.checkedIndices,
            prev.scoreboard,
            nextScoreboard,
            effectiveSourceUrl
          );
      const hadNoSource = !get().sourceUrl;
      set({
        ...(hadNoSource && effectiveSourceUrl === url
          ? { sourceUrl: url, sourceSrcdoc: data.srcdoc, sourceMessage: null }
          : {}),
        linkedUrl: data.linked_display_url,
        linkedSrcdoc: data.srcdoc,
        linkedMessage: data.body_message,
        scoreboard: nextScoreboard,
        scoreboardUrls: data.scoreboard_urls,
        folderPath: data.folder_path ?? get().folderPath,
        checkedIndices: checked,
        linkedIsBinary: isBinary,
        linkedBinaryUrl: isBinary ? data.linked_binary_url! : null,
        linkedBinaryReferrer: isBinary ? referrer : null,
        loading: false,
        error: null,
        downloadModalOpen: isBinary,
      });
      if (isBinary) {
        get().downloadBinary();
      }
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : "Failed to load",
        downloadModalOpen: false,
      });
    }
  },

  save: async () => {
    const { drpid, folderPath, scoreboardUrls, checkedIndices, metadata } = get();
    if (!drpid || !folderPath || checkedIndices.size === 0) return;
    set({ saveProgress: "Starting...", saveModalOpen: true });
    const form = new FormData();
    form.append("drpid", String(drpid));
    form.append("folder_path", folderPath);
    form.append("scoreboard_urls_json", JSON.stringify(scoreboardUrls));
    form.append("metadata_title", metadata.title);
    form.append("metadata_summary", metadata.summary);
    form.append("metadata_keywords", metadata.keywords);
    form.append("metadata_agency", metadata.agency);
    form.append("metadata_office", metadata.office);
    form.append("metadata_time_start", metadata.time_start);
    form.append("metadata_time_end", metadata.time_end);
    form.append("metadata_download_date", metadata.download_date);
    for (const idx of checkedIndices) {
      form.append("save_url", String(idx));
    }
    try {
      const res = await fetch(`${API}/save`, { method: "POST", body: form });
      if (!res.ok) {
        set({ saveProgress: `Error: ${await res.text()}`, saveModalOpen: true });
        return;
      }
      if (!res.body) {
        set({ saveProgress: "Done.", saveModalOpen: true });
        return;
      }
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
          if (line.startsWith("SAVING\t")) {
            const parts = line.split("\t");
            if (parts.length >= 4)
              set({ saveProgress: `Saving ${parts[1]} ${parts[2]}/${parts[3]}`, saveModalOpen: true });
          } else if (line.startsWith("DONE\t")) {
            const n = line.split("\t")[1] ?? "0";
            set({ saveProgress: `Saved ${n} file(s).`, saveModalOpen: true });
          } else if (line.startsWith("ERROR\t")) {
            set({ saveProgress: `Error: ${line.split("\t")[1] ?? "unknown"}`, saveModalOpen: true });
          }
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed";
      const isNetworkError =
        /network|failed to fetch|load failed|connection|timeout/i.test(msg) ||
        (e instanceof TypeError && msg.toLowerCase().includes("fetch"));
      set({
        saveProgress: isNetworkError
          ? "Connection lost. PDF conversion can take a long time—the server or network may have timed out. Check the terminal for details; try saving fewer pages at once."
          : `Error: ${msg}`,
        saveModalOpen: true,
      });
    }
  },

  closeSaveModal: () => set({ saveModalOpen: false }),

  closeDownloadModal: () => set({ downloadModalOpen: false }),

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

  clearScoreboard: async () => {
    try {
      const data = await fetchJson<{ scoreboard: ScoreboardNode[]; urls: string[] }>(
        `${API}/scoreboard/clear`,
        { method: "POST" }
      );
      set({
        scoreboard: data.scoreboard,
        scoreboardUrls: data.urls,
        checkedIndices: new Set(),
      });
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

  startDownloadsWatcher: async () => {
    const { drpid } = get();
    if (!drpid) return;
    try {
      const data = await fetchJson<{ ok: boolean; message?: string }>(`${API}/downloads-watcher/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ drpid }),
      });
      if (data.ok) {
        set({ downloadsWatcherActive: true });
      }
    } catch {
      // ignore - watcher may fail (e.g. watchdog not installed)
    }
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

  downloadBinary: async () => {
    const { linkedBinaryUrl, linkedBinaryReferrer, drpid } = get();
    if (!linkedBinaryUrl || !drpid) {
      set({ downloadProgress: "No project (DRPID) set. Load a project first.", downloadModalOpen: true });
      return;
    }
    set({ downloadProgress: "Downloading...", downloadModalOpen: true });
    const form = new FormData();
    form.append("url", linkedBinaryUrl);
    form.append("drpid", String(drpid));
    if (linkedBinaryReferrer) form.append("referrer", linkedBinaryReferrer);
    try {
      const res = await fetch(`${API}/download-file`, { method: "POST", body: form });
      if (!res.ok) {
        set({ downloadProgress: `Error ${res.status}: ${await res.text()}`, downloadModalOpen: true });
        return;
      }
      if (!res.body) {
        set({ downloadProgress: "Done.", downloadModalOpen: true });
        await get().refreshScoreboard();
        return;
      }
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
          if (line.startsWith("SAVING\t")) {
            const name = line.split("\t")[1] ?? "";
            set({ downloadProgress: `Downloading ${name}`, downloadModalOpen: true });
          } else if (line.startsWith("PROGRESS\t")) {
            const p = line.split("\t");
            const w = parseInt(p[1], 10);
            const t = p[2];
            const fmt = (n: number) =>
              n < 1024 ? `${n} B` : n < 1024 * 1024 ? `${(n / 1024).toFixed(1)} KB` : `${(n / (1024 * 1024)).toFixed(1)} MB`;
            set({
              downloadProgress: t ? `Downloaded ${fmt(w)} / ${fmt(parseInt(t, 10))}` : `Downloaded ${fmt(w)}`,
              downloadModalOpen: true,
            });
          } else if (line.startsWith("DONE\t")) {
            const name = line.split("\t")[1] ?? "";
            set({
              downloadProgress: name ? `Download complete. Saved as ${name}` : "Download complete.",
              downloadModalOpen: true,
            });
            await get().refreshScoreboard();
          } else if (line.startsWith("ERROR\t")) {
            set({ downloadProgress: `Error: ${line.split("\t")[1] ?? "unknown"}`, downloadModalOpen: true });
          }
        }
      }
    } catch (e) {
      set({
        downloadProgress: `Error: ${e instanceof Error ? e.message : "Failed"}`,
        downloadModalOpen: true,
      });
    }
  },

  loadProject: async (drpid) => {
    const proj = await fetchJson<{ source_url?: string }>(`${API}/projects/${drpid}`);
    if (proj.source_url) {
      await get().loadSource(proj.source_url, drpid);
    }
  },

  loadFirstProject: async () => {
    try {
      const proj = await fetchJson<{ source_url?: string; DRPID?: number }>(`${API}/projects/first`);
      if (proj.source_url && proj.DRPID != null) {
        await get().loadSource(proj.source_url, proj.DRPID);
      }
    } catch {
      // No eligible project (404) - leave state empty
    }
  },

  loadNext: async () => {
    const { drpid } = get();
    if (!drpid) return;
    const proj = await fetchJson<{ source_url?: string; DRPID?: number }>(
      `${API}/projects/next?current_drpid=${drpid}`
    );
    if (proj.source_url && proj.DRPID) {
      await get().loadSource(proj.source_url, proj.DRPID);
    }
  },
}));
