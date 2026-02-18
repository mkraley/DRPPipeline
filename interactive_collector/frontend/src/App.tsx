/**
 * AppShell - Main layout for the Interactive Collector SPA.
 *
 * Layout: top bar (Next, Load DRPID), left column (Scoreboard + Metadata),
 * and two panes (Source, Linked) for viewing pages.
 * Loads first eligible project from storage on startup.
 */
import { useCallback, useEffect, useRef } from "react";
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
  const { drpid, folderPath, loadProject, loadFirstProject, loadNext, save, loading } =
    useCollectorStore();
  const leftColRef = useRef<HTMLDivElement>(null);
  const splitterVRef = useRef<HTMLDivElement>(null);
  useLinkInterceptor();
  useHistorySync();

  useEffect(() => {
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
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const d = params.get("drpid");
    if (d) {
      const id = parseInt(d, 10);
      if (!isNaN(id)) loadProject(id);
    } else {
      loadFirstProject();
    }
  }, [loadProject, loadFirstProject]);

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

  return (
    <div className="app-shell">
      <header className="top">
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
          <SourcePane />
          <LinkedPane />
        </div>
      </div>
      <SaveProgressModal />
      <DownloadProgressModal />
    </div>
  );
}
