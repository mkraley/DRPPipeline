/**
 * LinkedPane - Iframe showing the currently selected linked page.
 *
 * Receives content from load-page API. Link clicks are intercepted and
 * trigger load-page for the new URL via postMessage from the iframe.
 * For non-HTML links (PDF, ZIP, etc.), shows referrer page and Download button.
 * Socrata/datadiscovery block iframe embedding, so we use srcdoc; use Open for full view.
 */
import { useState } from "react";
import { useCollectorStore } from "../store";

export function LinkedPane() {
  const {
    linkedUrl,
    linkedSrcdoc,
    linkedMessage,
    linkedIsBinary,
    downloadBinary,
    drpid,
    folderPath,
    sourceUrl,
    loadLinked,
    error,
  } = useCollectorStore();
  const canDownload = linkedIsBinary && drpid && folderPath;
  const [loadUrlInput, setLoadUrlInput] = useState("");

  const openInNewTab = () => {
    if (linkedUrl && /^https?:\/\//.test(linkedUrl)) window.open(linkedUrl, "_blank", "noopener,noreferrer");
  };

  const onLoadUrl = async () => {
    let url = loadUrlInput.trim();
    if (!url) return;
    if (!/^https?:\/\//.test(url)) url = "https://" + url;
    setLoadUrlInput("");
    await loadLinked(url, linkedUrl || sourceUrl || null);
  };

  return (
    <div className="pane">
      <div className="pane-header" title={linkedUrl}>
        <span className="pane-header-label">Linked:</span>
        {linkedUrl || "—"}
        {linkedUrl && (
          <button
            type="button"
            className="btn-open-external"
            onClick={openInNewTab}
            title="Open in new tab"
          >
            Open
          </button>
        )}
        {canDownload && (
          <button
            type="button"
            className="btn-download-binary"
            onClick={() => downloadBinary()}
            title="Download file to project folder"
          >
            Download
          </button>
        )}
      </div>
      {error && (
        <div className="pane-load-error" role="alert">
          {error}
        </div>
      )}
      <div className="pane-load-url">
        <input
          type="url"
          className="load-url-input"
          placeholder="Paste URL and load in pane"
          value={loadUrlInput}
          onChange={(e) => setLoadUrlInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onLoadUrl()}
        />
        <button type="button" className="btn-load-url" onClick={onLoadUrl} title="Load URL in pane">
          Load
        </button>
      </div>
      {linkedSrcdoc ? (
        <iframe
          className="pane-iframe"
          srcDoc={linkedSrcdoc}
          sandbox="allow-same-origin allow-scripts allow-forms allow-top-navigation-by-user-activation"
          title="Linked page"
        />
      ) : (
        <div className="pane-empty">
          {linkedMessage || "Click a link in Source (or Linked) to open it here."}
        </div>
      )}
    </div>
  );
}
