/**
 * LinkedPane - Iframe showing the currently selected linked page.
 *
 * Receives content from load-page API. Link clicks are intercepted and
 * trigger load-page for the new URL via postMessage from the iframe.
 */
import { useCollectorStore } from "../store";

export function LinkedPane() {
  const { linkedUrl, linkedSrcdoc, linkedMessage } = useCollectorStore();

  return (
    <div className="pane">
      <div className="pane-header" title={linkedUrl}>
        <span className="pane-header-label">Linked:</span> {linkedUrl || "—"}
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
