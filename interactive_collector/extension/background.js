/**
 * Background script: POST PDF to collector; browser print-to-PDF via debugger API.
 */
function postPdfToCollector(collectorBase, drpid, url, referrer, pdfBase64, pageTitle) {
  const binary = atob(pdfBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const blob = new Blob([bytes], { type: "application/pdf" });
  const fd = new FormData();
  fd.append("drpid", String(drpid));
  fd.append("url", url);
  fd.append("referrer", referrer || "");
  if (pageTitle && String(pageTitle).trim()) fd.append("title", String(pageTitle).trim());
  fd.append("pdf", blob, "page.pdf");
  return fetch(`${collectorBase}/api/extension/save-pdf`, {
    method: "POST",
    body: fd,
  }).then(r => r.json().catch(() => ({}))).then(data => ({
    ok: data.ok,
    error: data.error,
    filename: data.filename,
  }));
}

function getWatcherStatus(collectorBase) {
  return fetch(`${collectorBase}/api/downloads-watcher/status`)
    .then(r => r.json().catch(() => ({})))
    .then(data => ({ watching: !!data.watching }));
}

function stopWatcher(collectorBase) {
  return fetch(`${collectorBase}/api/downloads-watcher/stop`, { method: "POST" })
    .then(r => r.json().catch(() => ({})))
    .then(data => ({ ok: !!data.ok }));
}

function postMetadataFromPage(collectorBase, payload) {
  return fetch(`${collectorBase}/api/metadata-from-page`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(r => r.json().catch(() => ({}))).then(data => ({ ok: !!data.ok }));
}

/** Extract real PDF URL from tab URL (handles chrome-extension://id/https://... viewer URLs). */
function extractPdfUrl(tabUrl) {
  if (!tabUrl || typeof tabUrl !== "string") return null;
  const u = tabUrl.trim();
  const lower = u.toLowerCase();
  if (lower.endsWith(".pdf")) return u;
  const idx = u.indexOf("https://");
  if (idx !== -1) return u.slice(idx);
  const idxHttp = u.indexOf("http://");
  if (idxHttp !== -1) return u.slice(idxHttp);
  return null;
}

function isPdfUrl(url) {
  if (!url) return false;
  return url.toLowerCase().endsWith(".pdf") || /\.pdf(\?|#|$)/i.test(url);
}

/** Fetch PDF from url and POST to collector save-pdf. */
function fetchPdfAndPostToCollector(collectorBase, drpid, pdfUrl, referrer, pageTitle) {
  return fetch(pdfUrl, { method: "GET", credentials: "omit" })
    .then(r => {
      if (!r.ok) throw new Error("Fetch failed: " + r.status);
      return r.blob();
    })
    .then(blob => {
      if (!blob || blob.size === 0) throw new Error("Empty response");
      const fd = new FormData();
      fd.append("drpid", String(drpid));
      fd.append("url", pdfUrl);
      fd.append("referrer", referrer || "");
      if (pageTitle && String(pageTitle).trim()) fd.append("title", String(pageTitle).trim());
      const safeName = (pageTitle && pageTitle.length <= 80)
        ? (pageTitle.replace(/[^\w\s.-]/g, "_").replace(/\.[pP][dD][fF]$/, "").trim() || "document")
        : "document";
      fd.append("pdf", blob, (safeName.endsWith(".pdf") ? safeName : safeName + ".pdf"));
      return fetch(`${collectorBase}/api/extension/save-pdf`, { method: "POST", body: fd });
    })
    .then(r => r.json().catch(() => ({})))
    .then(data => ({ ok: !!data.ok, error: data.error, filename: data.filename }));
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "drp-save-this-pdf",
    title: "Save this PDF to DRP project",
    contexts: ["page"],
  });
  chrome.contextMenus.create({
    id: "drp-save-linked-pdf",
    title: "Save linked PDF to DRP project",
    contexts: ["link"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "drp-save-linked-pdf") {
    const pdfUrl = (info.linkUrl || "").trim();
    if (!isPdfUrl(pdfUrl)) {
      console.warn("[DRP] Not a PDF link:", pdfUrl);
      return;
    }
    chrome.storage.local.get(["drpid", "collectorBase"]).then(stored => {
      if (!stored.drpid || !stored.collectorBase) {
        console.warn("[DRP] No project context (use Copy & Open first)");
        return;
      }
      fetchPdfAndPostToCollector(stored.collectorBase, stored.drpid, pdfUrl, tab && tab.url ? tab.url : null, null)
        .then(result => { if (result.ok) console.log("[DRP] PDF saved:", result.filename); else console.warn("[DRP] Save failed:", result.error); })
        .catch(e => console.warn("[DRP] Save failed:", e));
    });
    return;
  }
  if (info.menuItemId === "drp-save-this-pdf" && tab && tab.id) {
    const tabUrl = (tab.url || "").trim();
    const pdfUrl = extractPdfUrl(tabUrl) || (isPdfUrl(tabUrl) ? tabUrl : null);
    if (!pdfUrl) {
      console.warn("[DRP] Current tab is not a PDF:", tabUrl);
      return;
    }
    chrome.storage.local.get(["drpid", "collectorBase"]).then(stored => {
      if (!stored.drpid || !stored.collectorBase) {
        console.warn("[DRP] No project context (use Copy & Open first)");
        return;
      }
      const pageTitle = (tab.title || "").trim();
      fetchPdfAndPostToCollector(stored.collectorBase, stored.drpid, pdfUrl, null, pageTitle)
        .then(result => { if (result.ok) console.log("[DRP] PDF saved:", result.filename); else console.warn("[DRP] Save failed:", result.error); })
        .catch(e => console.warn("[DRP] Save failed:", e));
    });
  }
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "drp-watcher-status") {
    const { collectorBase } = msg;
    if (!collectorBase) {
      sendResponse({ watching: false });
      return true;
    }
    getWatcherStatus(collectorBase).then(sendResponse).catch(() => sendResponse({ watching: false }));
    return true;
  }
  if (msg.type === "drp-watcher-stop") {
    const { collectorBase } = msg;
    if (!collectorBase) {
      sendResponse({ ok: false });
      return true;
    }
    stopWatcher(collectorBase).then(sendResponse).catch(() => sendResponse({ ok: false }));
    return true;
  }
  if (msg.type === "drp-save-pdf") {
    const { collectorBase, drpid, url, referrer, pdfBase64, title } = msg;
    if (!collectorBase || !drpid || !url || !pdfBase64) {
      sendResponse({ ok: false, error: "Missing data" });
      return true;
    }
    (async () => {
      try {
        const data = await postPdfToCollector(collectorBase, drpid, url, referrer || "", pdfBase64, title);
        sendResponse(data);
      } catch (e) {
        sendResponse({ ok: false, error: String(e && e.message || e) });
      }
    })();
    return true;
  }

  if (msg.type === "drp-metadata-from-page") {
    const { collectorBase, payload } = msg;
    console.log("[DRP meta] background: received metadata-from-page", { collectorBase, drpid: payload && payload.drpid, keys: payload && Object.keys(payload) });
    if (!collectorBase || !payload) {
      console.log("[DRP meta] background: bail missing collectorBase or payload");
      sendResponse({ ok: false });
      return true;
    }
    postMetadataFromPage(collectorBase, payload)
      .then((data) => {
        console.log("[DRP meta] background: POST result", data);
        sendResponse(data);
      })
      .catch((err) => {
        console.log("[DRP meta] background: POST failed", err);
        sendResponse({ ok: false });
      });
    return true;
  }
  if (msg.type === "drp-fetch-pdf-to-project") {
    const { pdfUrl } = msg;
    if (!pdfUrl || typeof pdfUrl !== "string") {
      sendResponse({ ok: false, error: "pdfUrl required" });
      return true;
    }
    (async () => {
      try {
        const stored = await chrome.storage.local.get(["drpid", "collectorBase"]);
        if (!stored.drpid || !stored.collectorBase) {
          sendResponse({ ok: false, error: "No project context (use Copy & Open first)" });
          return;
        }
        const result = await fetchPdfAndPostToCollector(stored.collectorBase, stored.drpid, pdfUrl, msg.referrer || null, msg.pageTitle || null);
        sendResponse(result);
      } catch (e) {
        sendResponse({ ok: false, error: String(e && e.message || e) });
      }
    })();
    return true;
  }
  if (msg.type === "drp-print-to-pdf") {
    const { collectorBase, drpid, url, referrer, title } = msg;
    const tabId = sender.tab && sender.tab.id;
    if (!collectorBase || !drpid || !url || tabId == null) {
      sendResponse({ ok: false, error: "Missing data", fallback: true });
      return true;
    }
    (async () => {
      try {
        chrome.debugger.attach({ tabId }, "1.3");
        try {
          await chrome.debugger.sendCommand({ tabId }, "Page.enable");
          const res = await chrome.debugger.sendCommand({ tabId }, "Page.printToPDF", {
            printBackground: true,
            preferCSSPageSize: true,
          });
          const pdfBase64 = res && res.data;
          if (!pdfBase64) {
            sendResponse({ ok: false, error: "No PDF data", fallback: true });
            return;
          }
          const data = await postPdfToCollector(collectorBase, drpid, url, referrer || "", pdfBase64, title);
          sendResponse(data);
        } finally {
          try {
            chrome.debugger.detach({ tabId });
          } catch (_) {}
        }
      } catch (e) {
        sendResponse({
          ok: false,
          error: String(e && e.message || e),
          fallback: true,
        });
      }
    })();
    return true;
  }
});
