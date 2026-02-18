/**
 * MetadataForm - Title, summary, keywords, agency, dates.
 *
 * Values are synced with the store and persisted to Storage on Save.
 * Description is rich text (contentEditable). Keywords converts spaces to "; " on paste/blur.
 */
import { useCallback, useEffect, useRef } from "react";
import { useCollectorStore } from "../store";

const STORAGE_KEY = "metadata_draft_";

/** Convert spaces to "; " when no commas or semicolons present. */
function normalizeKeywords(value: string): string {
  const trimmed = value.replace(/\s+/g, " ").trim();
  if (!trimmed) return "";
  if (/[;,]/.test(trimmed)) return value;
  if (/\s/.test(trimmed)) {
    return trimmed.split(/\s+/).filter(Boolean).join("; ");
  }
  return value;
}

export function MetadataForm() {
  const { drpid, metadata, setMetadata } = useCollectorStore();
  const summaryEditorRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLTextAreaElement>(null);
  const titleResizerRef = useRef<HTMLDivElement>(null);

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

  // Title textarea resize handle
  useEffect(() => {
    const grip = titleResizerRef.current;
    const target = titleRef.current;
    if (!grip || !target) return;
    const minH = 40;
    const handleMouseDown = (e: MouseEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      const startY = e.clientY;
      const startH = target.offsetHeight;
      const move = (e2: MouseEvent) => {
        const dy = e2.clientY - startY;
        target.style.height = `${Math.max(minH, startH + dy)}px`;
      };
      const stop = () => {
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", stop);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };
      document.body.style.cursor = "nwse-resize";
      document.body.style.userSelect = "none";
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", stop);
    };
    grip.addEventListener("mousedown", handleMouseDown);
    return () => grip.removeEventListener("mousedown", handleMouseDown);
  }, []);

  // Sync summary editor innerHTML when metadata.summary changes externally
  useEffect(() => {
    const el = summaryEditorRef.current;
    if (!el) return;
    if (el.innerHTML !== metadata.summary) {
      el.innerHTML = metadata.summary || "";
    }
  }, [metadata.summary]);

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
      const key = name.replace("metadata_", "") as keyof typeof metadata;
      setMetadata({ [key]: value });
      saveDraft();
    },
    [setMetadata, saveDraft]
  );

  const handleSummaryInput = useCallback(() => {
    const el = summaryEditorRef.current;
    if (!el) return;
    setMetadata({ summary: el.innerHTML });
    saveDraft();
  }, [setMetadata, saveDraft]);

  const handleSummaryToolbar = useCallback((cmd: string) => {
    document.execCommand(cmd, false);
    summaryEditorRef.current?.focus();
  }, []);

  const handleKeywordsBlur = useCallback(
    (e: React.FocusEvent<HTMLTextAreaElement>) => {
      const val = e.target.value;
      const normalized = normalizeKeywords(val);
      if (normalized !== val) {
        setMetadata({ keywords: normalized });
        saveDraft();
      }
    },
    [setMetadata, saveDraft]
  );

  const handleKeywordsPaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      e.preventDefault();
      const text = e.clipboardData.getData("text/plain") || "";
      const normalized = normalizeKeywords(text);
      const ta = e.currentTarget;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const val = ta.value;
      const newVal = val.slice(0, start) + normalized + val.slice(end);
      setMetadata({ keywords: newVal });
      saveDraft();
    },
    [setMetadata, saveDraft]
  );

  return (
    <div className="metadata-pane">
      <h3>Metadata</h3>
      <label htmlFor="metadata-title">Title</label>
      <div className="metadata-title-wrap resizer-wrap">
        <textarea
          id="metadata-title"
          name="metadata_title"
          value={metadata.title}
          onChange={handleChange}
          rows={2}
          ref={titleRef}
        />
        <div
          className="triangle-resizer"
          ref={titleResizerRef}
          title="Drag to resize"
          aria-label="Resize"
        />
      </div>
      <label htmlFor="metadata-summary-editor">Description</label>
      <div className="metadata-richtext-wrap">
        <div className="metadata-richtext-toolbar" aria-label="Formatting">
          <button type="button" onClick={() => handleSummaryToolbar("bold")} title="Bold">
            B
          </button>
          <button type="button" onClick={() => handleSummaryToolbar("italic")} title="Italic">
            I
          </button>
          <button type="button" onClick={() => handleSummaryToolbar("underline")} title="Underline">
            U
          </button>
          <button type="button" onClick={() => handleSummaryToolbar("insertUnorderedList")} title="Bullet list">
            • List
          </button>
        </div>
        <div
          ref={summaryEditorRef}
          id="metadata-summary-editor"
          className="metadata-richtext-editor"
          contentEditable
          data-placeholder="Summary"
          role="textbox"
          onInput={handleSummaryInput}
          onBlur={handleSummaryInput}
          suppressContentEditableWarning
        />
      </div>
      <label htmlFor="metadata-keywords">Keywords</label>
      <textarea
        id="metadata-keywords"
        name="metadata_keywords"
        value={metadata.keywords}
        onChange={handleChange}
        onBlur={handleKeywordsBlur}
        onPaste={handleKeywordsPaste}
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
