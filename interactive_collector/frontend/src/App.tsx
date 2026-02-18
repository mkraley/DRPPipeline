/**
 * AppShell - Main layout for the Interactive Collector SPA.
 *
 * Two views: Main page (pipeline launcher) and Collector (scoreboard + Source/Linked panes).
 * Default view is Main; "Interactive collector" opens Collector; "Back to main" returns.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { MainPage } from "./components/MainPage";
import { Scoreboard } from "./components/Scoreboard";
import { MetadataForm } from "./components/MetadataForm";
import { SourcePane } from "./components/SourcePane";
import { LinkedPane } from "./components/LinkedPane";
import { SaveProgressModal } from "./components/SaveProgressModal";
import { DownloadProgressModal } from "./components/DownloadProgressModal";
import { useCollectorStore } from "./store";
import { useHistorySync } from "./useHistorySync";
import { useLinkInterceptor } from "./useLinkInterceptor";

export default function App() {
  const [view, setView] = useState<"main" | "collector">("main");
  const { drpid, folderPath, loadProject, loadFirstProject, loadNext, save, loading } =
    useCollectorStore();
  const leftColRef = useRef<HTMLDivElement>(null);
  const splitterVRef = useRef<HTMLDivElement>(null);
  useLinkInterceptor();
  useHistorySync();

  useEffect(() => {
    if (view !== "collector") return;
    const splitter = splitterVRef.current;
    const leftCol = leftColRef.current;
    if (!splitter || !leftCol) return;
    const main = leftCol.closest(".main");
    if (!main) return;
    const handleMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const move = (e2: MouseEvent) => {
        const r = main!.getBoundingClientRect();
        const w = Math.max(180, Math.min(r.width * 0.5, e2.clientX - r.left));
        leftCol!.style.width = `${w}px`;
      };
      const stop = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", stop);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };
      document.body.style.cursor = getComputedStyle(splitter).cursor;
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", stop);
    };
    splitter.addEventListener("mousedown", handleMouseDown);
    return () => splitter.removeEventListener("mousedown", handleMouseDown);
  }, [view]);

  useEffect(() => {
    if (view !== "collector") return;
    const params = new URLSearchParams(window.location.search);
    const d = params.get("drpid");
    if (d) {
      const id = parseInt(d, 10);
      if (!isNaN(id)) loadProject(id);
    } else {
      loadFirstProject();
    }
  }, [view, loadProject, loadFirstProject]);

  const onLoadDrpidSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const form = e.currentTarget;
      const val = (form.querySelector('input[name="load_drpid"]') as HTMLInputElement)?.value?.trim();
      if (val) {
        const id = parseInt(val, 10);
        if (!isNaN(id)) loadProject(id);
      }
    },
    [loadProject]
  );

  const onOpenCollector = useCallback((initialDrpid?: number) => {
    if (initialDrpid != null && !isNaN(initialDrpid)) {
      const params = new URLSearchParams(window.location.search);
      params.set("drpid", String(initialDrpid));
      window.history.replaceState(
        { drpid: initialDrpid },
        "",
        `${window.location.pathname}?${params.toString()}`
      );
    }
    setView("collector");
  }, []);

  if (view === "main") {
    return <MainPage onOpenCollector={onOpenCollector} />;
  }

  return (
    <div className="app-shell">
      <header className="top">
        <button type="button" className="main-page-back-btn" onClick={() => setView("main")}>
          Back to main
        </button>
        {drpid != null && (
          <>
            <span className="drpid">DRPID: {drpid}</span>
            <button type="button" onClick={loadNext}>
              Next
            </button>
          </>
        )}
        <form className="top-form" onSubmit={onLoadDrpidSubmit}>
          <label htmlFor="load_drpid">Load DRPID</label>
          <input
            type="number"
            id="load_drpid"
            name="load_drpid"
            placeholder="e.g. 1"
            min={1}
            max={99999}
            className="top-input-drpid"
          />
          <button type="submit">Load</button>
        </form>
        {folderPath && (
          <button type="button" className="btn-save" onClick={save} disabled={loading}>
            Save
          </button>
        )}
      </header>
      <div className="main">
        <div className="left-col" ref={leftColRef}>
          <Scoreboard />
          <div className="splitter splitter-h" title="Drag to resize scoreboard" />
          <MetadataForm />
        </div>
        <div className="splitter splitter-v" ref={splitterVRef} title="Drag to resize left column" />
        <div className="panes">
          {drpid == null && !loading && (
            <div className="collector-empty-state">
              No project loaded. Use <strong>Load DRPID</strong> below to open a project, or run the{" "}
              <strong>sourcing</strong> module from the main page to add candidates.
            </div>
          )}
          <div className="panes-row">
            <SourcePane />
            <LinkedPane />
          </div>
        </div>
      </div>
      <SaveProgressModal />
      <DownloadProgressModal />
    </div>
  );
}
