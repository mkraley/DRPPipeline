/**
 * NoLinksConfirmModal - Confirmation dialog shown after "No Links" is pressed.
 */
import { useCollectorStore } from "../store";

export function NoLinksConfirmModal() {
  const { noLinksModalOpen, closeNoLinksModal } = useCollectorStore();
  if (!noLinksModalOpen) return null;
  return (
    <div className="save-modal show" role="dialog" aria-label="No links confirmation">
      <div className="save-modal-dialog">
        <strong>No Links</strong>
        <div className="save-modal-message">Project marked as having no live links.</div>
        <button type="button" className="save-modal-ok" onClick={closeNoLinksModal}>
          Close
        </button>
      </div>
    </div>
  );
}
