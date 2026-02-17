/**
 * AppShell - Main layout for the Interactive Collector SPA.
 *
 * Layout: top bar (URL input, Next, Load DRPID), left column (Scoreboard + Metadata),
 * and two panes (Source, Linked) for viewing pages.
 */
import { useCallback } from "react";
import { Scoreboard } from "./components/Scoreboard";
import { MetadataForm } from "./components/MetadataForm";
import { SourcePane } from "./components/SourcePane";
import { LinkedPane } from "./components/LinkedPane";
import { SaveProgressModal } from "./components/SaveProgressModal";
import { useCollectorStore } from "./store";
import { useHistorySync } from "./useHistorySync";
import { useLinkInterceptor } from "./useLinkInterceptor";

export default function App() {
  const { drpid, loadSource, loadProject, loadNext } = useCollectorStore();
  useLinkInterceptor();
  useHistorySync();

  const onUrlSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();
      const form = e.currentTarget;
      const url = (form.querySelector('input[name="url"]') as HTMLInputElement)?.value?.trim();
      if (url) loadSource(url, drpid);
    },
    [drpid, loadSource]
  );

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
            <span className="top-sep">|</span>
            <button type="button" onClick={loadNext}>
              Next
            </button>
            <span className="top-sep">|</span>
          </>
        )}
        <form className="top-form" onSubmit={onUrlSubmit}>
          <label htmlFor="url">URL:</label>
          <input type="url" id="url" name="url" placeholder="https://example.com" />
          <button type="submit">Go</button>
        </form>
        <span className="top-sep">|</span>
        <form className="top-form" onSubmit={onLoadDrpidSubmit}>
          <label htmlFor="load_drpid">Load DRPID:</label>
          <input type="number" id="load_drpid" name="load_drpid" placeholder="e.g. 1" min={1} />
          <button type="submit">Load</button>
        </form>
      </header>
      <div className="main">
        <div className="left-col">
          <Scoreboard />
          <div className="splitter splitter-h" title="Drag to resize scoreboard" />
          <MetadataForm />
        </div>
        <div className="splitter splitter-v" title="Drag to resize left column" />
        <div className="panes">
          <SourcePane />
          <LinkedPane />
        </div>
      </div>
      <SaveProgressModal />
    </div>
  );
}
