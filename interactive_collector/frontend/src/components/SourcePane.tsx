/**
 * SourcePane - Iframe showing the original source page.
 *
 * Uses srcdoc with link interceptor; clicks load in the Linked pane.
 * Socrata/datadiscovery block iframe embedding, so we always use srcdoc.
 */
import { useState, useCallback, useEffect } from "react";
import { useCollectorStore } from "../store";

export function SourcePane() {
  const { sourceUrl, sourceSrcdoc, sourceMessage, drpid } = useCollectorStore();
  const [toast, setToast] = useState<string | null>(null);

  const openInNewTab = () => {
    if (sourceUrl && /^https?:\/\//.test(sourceUrl)) window.open(sourceUrl, "_blank", "noopener,noreferrer");
  };

  const { startDownloadsWatcher } = useCollectorStore();
  const copyAndOpen = useCallback(async () => {
    if (!sourceUrl || !drpid || !/^https?:\/\//.test(sourceUrl)) return;
    const launcher = `${window.location.origin}/extension/launcher?drpid=${drpid}&url=${encodeURIComponent(sourceUrl)}`;
    try {
      await navigator.clipboard.writeText(launcher);
      setToast("Copied! Paste in browser. Watching Downloads folder.");
      await startDownloadsWatcher();
    } catch {
      window.prompt("Copy this URL and paste in extended browser:", launcher);
    }
  }, [sourceUrl, drpid, startDownloadsWatcher]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="pane source-pane">
      {toast && <div className="copy-open-toast">{toast}</div>}
      <div className="pane-header" title={sourceUrl}>
        Source: {sourceUrl || "—"}
        {sourceUrl && (
          <>
            <button
              type="button"
              className="btn-open-external"
              onClick={openInNewTab}
              title="Open in new tab"
            >
              Open
            </button>
            {drpid != null && (
              <button
                type="button"
                className="btn-open-external"
                onClick={copyAndOpen}
                title="Copy launcher URL to paste in extended browser (with extension)"
              >
                Copy &amp; Open
              </button>
            )}
          </>
        )}
      </div>
      {sourceSrcdoc ? (
        <iframe
          className="pane-iframe"
          srcDoc={sourceSrcdoc}
          sandbox="allow-same-origin allow-scripts allow-forms allow-top-navigation-by-user-activation"
          title="Source page"
          data-drp-source-pane="true"
          data-source-url={sourceUrl || ""}
        />
      ) : (
        <div className="pane-empty">
          {sourceMessage || "Enter a URL and click Go, or click a link to open it in the Linked pane."}
        </div>
      )}
    </div>
  );
}
