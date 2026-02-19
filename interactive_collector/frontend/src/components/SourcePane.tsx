/**
 * SourcePane - Iframe showing the original source page.
 *
 * Uses srcdoc with link interceptor; clicks load in the Linked pane.
 * Socrata/datadiscovery block iframe embedding, so we always use srcdoc.
 */
import { useCollectorStore } from "../store";

export function SourcePane() {
  const { sourceUrl, sourceSrcdoc, sourceMessage } = useCollectorStore();

  const openInNewTab = () => {
    if (sourceUrl && /^https?:\/\//.test(sourceUrl)) window.open(sourceUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="pane source-pane">
      <div className="pane-header" title={sourceUrl}>
        Source: {sourceUrl || "—"}
        {sourceUrl && (
          <button
            type="button"
            className="btn-open-external"
            onClick={openInNewTab}
            title="Open in new tab"
          >
            Open
          </button>
        )}
      </div>
      {sourceSrcdoc ? (
        <iframe
          className="pane-iframe"
          srcDoc={sourceSrcdoc}
          sandbox="allow-same-origin allow-scripts allow-forms allow-top-navigation-by-user-activation"
          title="Source page"
        />
      ) : (
        <div className="pane-empty">
          {sourceMessage || "Enter a URL and click Go, or click a link to open it in the Linked pane."}
        </div>
      )}
    </div>
  );
}
