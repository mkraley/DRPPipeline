/**
 * SaveProgressModal - Displays save progress (SAVING, DONE, ERROR).
 */
import { useCollectorStore } from "../store";

export function SaveProgressModal() {
  const { saveModalOpen, saveProgress, closeSaveModal } = useCollectorStore();
  if (!saveModalOpen) return null;
  return (
    <div className="save-modal show" role="dialog" aria-label="Save progress">
      <div className="save-modal-dialog">
        <strong>Saving PDFs</strong>
        <div className="save-modal-message">{saveProgress}</div>
        <button type="button" className="save-modal-ok" onClick={closeSaveModal}>
          Close
        </button>
      </div>
    </div>
  );
}
