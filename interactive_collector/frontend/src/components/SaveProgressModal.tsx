/**
 * SaveProgressModal - Displays save progress (SAVING, DONE, ERROR).
 * Close button hidden until operation completes.
 */
import { useCollectorStore } from "../store";

export function SaveProgressModal() {
  const { saveModalOpen, saveProgress, closeSaveModal } = useCollectorStore();
  const isComplete =
    saveProgress.startsWith("Saved") || saveProgress.startsWith("Error") || saveProgress.startsWith("Done");
  if (!saveModalOpen) return null;
  return (
    <div className="save-modal show" role="dialog" aria-label="Save progress">
      <div className="save-modal-dialog">
        <strong>Saving PDFs</strong>
        <div className="save-modal-message">{saveProgress}</div>
        {isComplete && (
          <button type="button" className="save-modal-ok" onClick={closeSaveModal}>
            Close
          </button>
        )}
      </div>
    </div>
  );
}
