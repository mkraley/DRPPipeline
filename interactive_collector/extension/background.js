/**
 * Background script: POST PDF to collector (avoids CORS issues).
 */
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type !== "drp-save-pdf") return;
  const { collectorBase, drpid, url, referrer, pdfBase64 } = msg;
  if (!collectorBase || !drpid || !url || !pdfBase64) {
    sendResponse({ ok: false, error: "Missing data" });
    return true;
  }
  (async () => {
    try {
      const binary = atob(pdfBase64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const blob = new Blob([bytes], { type: "application/pdf" });
      const fd = new FormData();
      fd.append("drpid", String(drpid));
      fd.append("url", url);
      fd.append("referrer", referrer || "");
      fd.append("pdf", blob, "page.pdf");
      const r = await fetch(`${collectorBase}/api/extension/save-pdf`, {
        method: "POST",
        body: fd,
      });
      const data = await r.json().catch(() => ({}));
      sendResponse({ ok: r.ok && data.ok, error: data.error, filename: data.filename });
    } catch (e) {
      sendResponse({ ok: false, error: String(e && e.message || e) });
    }
  })();
  return true;
});
