/**
 * MetadataForm - Title, summary, keywords, agency, dates.
 *
 * Values are synced with the store and persisted to Storage on Save.
 */
import { useCallback, useEffect } from "react";
import { useCollectorStore } from "../store";

const STORAGE_KEY = "metadata_draft_";

export function MetadataForm() {
  const { drpid, metadata, setMetadata } = useCollectorStore();

  // Restore draft from sessionStorage when drpid changes
  useEffect(() => {
    if (!drpid) return;
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY + drpid);
      if (raw) {
        const draft = JSON.parse(raw) as Partial<typeof metadata>;
        setMetadata(draft);
      }
    } catch {
      /* ignore */
    }
  }, [drpid, setMetadata]);

  const saveDraft = useCallback(() => {
    if (!drpid) return;
    try {
      sessionStorage.setItem(STORAGE_KEY + drpid, JSON.stringify(metadata));
    } catch {
      /* ignore */
    }
  }, [drpid, metadata]);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const { name, value } = e.target;
      setMetadata({ [name.replace("metadata_", "") as keyof typeof metadata]: value });
      saveDraft();
    },
    [setMetadata, saveDraft]
  );

  return (
    <div className="metadata-pane">
      <h3>Metadata</h3>
      <label htmlFor="metadata-title">Title</label>
      <input
        type="text"
        id="metadata-title"
        name="metadata_title"
        value={metadata.title}
        onChange={handleChange}
      />
      <label htmlFor="metadata-summary">Description</label>
      <textarea
        id="metadata-summary"
        name="metadata_summary"
        value={metadata.summary}
        onChange={handleChange}
        rows={3}
      />
      <label htmlFor="metadata-keywords">Keywords</label>
      <textarea
        id="metadata-keywords"
        name="metadata_keywords"
        value={metadata.keywords}
        onChange={handleChange}
        rows={2}
      />
      <label htmlFor="metadata-agency">Agency</label>
      <input
        type="text"
        id="metadata-agency"
        name="metadata_agency"
        value={metadata.agency}
        onChange={handleChange}
      />
      <label htmlFor="metadata-office">Office</label>
      <input
        type="text"
        id="metadata-office"
        name="metadata_office"
        value={metadata.office}
        onChange={handleChange}
      />
      <label htmlFor="metadata-time-start">Start Date</label>
      <input
        type="text"
        id="metadata-time-start"
        name="metadata_time_start"
        value={metadata.time_start}
        onChange={handleChange}
        placeholder="YYYY-MM-DD or YYYY"
      />
      <label htmlFor="metadata-time-end">End Date</label>
      <input
        type="text"
        id="metadata-time-end"
        name="metadata_time_end"
        value={metadata.time_end}
        onChange={handleChange}
        placeholder="YYYY-MM-DD or YYYY"
      />
      <label htmlFor="metadata-download-date">Download date</label>
      <input
        type="text"
        id="metadata-download-date"
        name="metadata_download_date"
        value={metadata.download_date}
        onChange={handleChange}
        placeholder="YYYY-MM-DD"
      />
    </div>
  );
}
