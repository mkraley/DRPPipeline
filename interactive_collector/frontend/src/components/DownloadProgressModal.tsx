/**
 * DownloadProgressModal - Displays file download progress (SAVING, DONE, ERROR).
 * Close button hidden until operation completes.
 */
import { useCollectorStore } from "../store";

export function DownloadProgressModal() {
  const { downloadModalOpen, downloadProgress, closeDownloadModal } = useCollectorStore();
  const isComplete =
    downloadProgress.startsWith("Download complete") ||
    downloadProgress.startsWith("Error") ||
    downloadProgress.startsWith("No project");
  if (!downloadModalOpen) return null;
  return (
    <div className="save-modal show" role="dialog" aria-label="Download progress">
      <div className="save-modal-dialog">
        <strong>Downloading file</strong>
        <div className="save-modal-message">{downloadProgress}</div>
        {isComplete && (
          <button type="button" className="save-modal-ok" onClick={closeDownloadModal}>
            Close
          </button>
        )}
      </div>
    </div>
  );
}
