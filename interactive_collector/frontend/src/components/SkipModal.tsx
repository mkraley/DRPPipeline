/**
 * SkipModal - Reason text or preset skip types.
 */
import { useState } from "react";
import { useCollectorStore } from "../store";

const SKIP_PRESETS = ["no dataset", "gigantic upload", "needs scripting"] as const;
type SkipPreset = (typeof SKIP_PRESETS)[number];

export function SkipModal() {
  const { skipModalOpen, closeSkipModal, skip } = useCollectorStore();
  const [reason, setReason] = useState("");
  const [preset, setPreset] = useState<SkipPreset | "">("");
  const [submitError, setSubmitError] = useState("");

  if (!skipModalOpen) return null;

  const canSubmit = Boolean(preset || reason.trim());

  const handlePresetChange = (value: SkipPreset, checked: boolean) => {
    if (checked) {
      setPreset(value);
      setReason("");
    } else if (preset === value) {
      setPreset("");
    }
  };

  const handleReasonChange = (value: string) => {
    setReason(value);
    if (value.trim()) {
      setPreset("");
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitError("");
    try {
      await skip({ reason: reason.trim(), skipType: preset || undefined });
      setReason("");
      setPreset("");
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Skip failed");
    }
  };

  const handleCancel = () => {
    setReason("");
    setPreset("");
    setSubmitError("");
    closeSkipModal();
  };

  return (
    <div className="save-modal show" role="dialog" aria-label="Skip reason">
      <div className="save-modal-dialog">
        <strong>Skip</strong>
        <form onSubmit={handleSubmit}>
          <fieldset className="skip-preset-options">
            <legend>Skip type</legend>
            {SKIP_PRESETS.map((value) => (
              <label key={value} className="collector-load-option">
                <input
                  type="checkbox"
                  checked={preset === value}
                  onChange={(e) => handlePresetChange(value, e.target.checked)}
                />
                {value.charAt(0).toUpperCase() + value.slice(1)}
              </label>
            ))}
          </fieldset>
          <label htmlFor="skip-reason">Reason (hold for later)</label>
          <input
            id="skip-reason"
            type="text"
            value={reason}
            onChange={(e) => handleReasonChange(e.target.value)}
            placeholder="e.g. waiting on requester"
            className="save-modal-input"
            disabled={Boolean(preset)}
            autoFocus={!preset}
          />
          {submitError && <p className="save-modal-error">{submitError}</p>}
          <div className="save-modal-actions">
            <button type="button" className="save-modal-ok" onClick={handleCancel}>
              Cancel
            </button>
            <button type="submit" className="save-modal-ok" disabled={!canSubmit}>
              Submit
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
