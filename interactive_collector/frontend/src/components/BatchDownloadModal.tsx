/**
 * BatchDownloadModal - Progress for "Download all data links" with pause/resume/cancel.
 */
import { useCollectorStore } from "../store";

export function BatchDownloadModal() {
  const {
    batchModalOpen,
    batchProgress,
    batchJobId,
    batchPaused,
    batchRunning,
    pauseBatchDownload,
    resumeBatchDownload,
    cancelBatchDownload,
    closeBatchModal,
  } = useCollectorStore();

  const isComplete =
    batchProgress.startsWith("Done:") ||
    batchProgress.startsWith("Cancelled") ||
    batchProgress.startsWith("Error:");

  if (!batchModalOpen) return null;

  return (
    <div className="save-modal show" role="dialog" aria-label="Batch download progress">
      <div className="save-modal-dialog">
        <strong>Download all data links</strong>
        <div className="save-modal-message">{batchProgress}</div>
        {batchRunning && batchJobId && (
          <div className="batch-modal-controls">
            {batchPaused ? (
              <button type="button" className="btn-top" onClick={() => resumeBatchDownload()}>
                Resume
              </button>
            ) : (
              <button type="button" className="btn-top" onClick={() => pauseBatchDownload()}>
                Pause
              </button>
            )}
            <button type="button" className="btn-top" onClick={() => cancelBatchDownload()}>
              Cancel
            </button>
          </div>
        )}
        {isComplete && (
          <button type="button" className="save-modal-ok" onClick={closeBatchModal}>
            Close
          </button>
        )}
      </div>
    </div>
  );
}
