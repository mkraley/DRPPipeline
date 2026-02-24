/**
 * SourcePane - Displays source URL and Copy & Open button.
 *
 * User pastes the launcher URL in the extended browser to browse with the
 * extension. No iframe display of the source page.
 */
import { useState, useCallback, useEffect } from "react";
import { useCollectorStore } from "../store";

export function SourcePane() {
  const { sourceUrl, drpid } = useCollectorStore();
  const [toast, setToast] = useState<string | null>(null);

  const { startDownloadsWatcher } = useCollectorStore();
  const copyAndOpen = useCallback(async () => {
    if (!sourceUrl || !drpid || !/^https?:\/\//.test(sourceUrl)) return;
    const launcher = `${window.location.origin}/extension/launcher?drpid=${drpid}&url=${encodeURIComponent(sourceUrl)}`;
    try {
      await startDownloadsWatcher();
      await navigator.clipboard.writeText(launcher);
      setToast("Copied! Paste in browser. Save as PDF and downloads watching are on.");
    } catch {
      try {
        await navigator.clipboard.writeText(launcher);
        setToast("URL copied. Watcher could not start — paste in browser to use Save as PDF.");
      } catch {
        window.prompt("Copy this URL and paste in extended browser:", launcher);
      }
    }
  }, [sourceUrl, drpid, startDownloadsWatcher]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="pane source-pane source-pane-simple">
      {toast && <div className="copy-open-toast">{toast}</div>}
      <div className="pane-header" title={sourceUrl || ""}>
        Source: {sourceUrl || "—"}
        {sourceUrl && drpid != null && (
              <button
                type="button"
                className="btn-open-external btn-copy-open"
                onClick={copyAndOpen}
                title="Copy launcher URL to paste in extended browser (with extension)"
              >
                Copy &amp; Open
              </button>
        )}
      </div>
      <div className="pane-empty">
        Use <strong>Copy &amp; Open</strong> to copy the launcher URL, then paste it in your
        browser with the extension installed. Browse there and save pages as PDF.
      </div>
    </div>
  );
}
