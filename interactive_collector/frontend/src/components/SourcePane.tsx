/**
 * SourcePane - Iframe showing the original source page.
 *
 * Links are intercepted via postMessage; clicks load in the Linked pane
 * without full page reload.
 */
import { useCollectorStore } from "../store";

export function SourcePane() {
  const { sourceUrl, sourceSrcdoc, sourceMessage } = useCollectorStore();

  return (
    <div className="pane source-pane">
      <div className="pane-header" title={sourceUrl}>
        Source: {sourceUrl || "—"}
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
