/**
 * Interactive Collector SPA.
 *
 * Single view: Main page. Left column = pipeline controls and module buttons.
 * Right pane = Log output (when running sourcing etc.) or Collector (Scoreboard,
 * Metadata, Copy & Open in top rail) when "Interactive collector" is active.
 */
import { useEffect } from "react";
import { MainPage } from "./components/MainPage";
import { SaveProgressModal } from "./components/SaveProgressModal";
import { NoLinksConfirmModal } from "./components/NoLinksConfirmModal";
import { useCollectorStore } from "./store";
import { useHistorySync } from "./useHistorySync";

export default function App() {
  const { drpid } = useCollectorStore();
  useHistorySync();

  useEffect(() => {
    document.title =
      drpid != null ? `DRP${String(drpid).padStart(6, "0")} - DRP Pipeline` : "DRP Pipeline";
  }, [drpid]);

  return (
    <>
      <MainPage />
      <SaveProgressModal />
      <NoLinksConfirmModal />
    </>
  );
}
