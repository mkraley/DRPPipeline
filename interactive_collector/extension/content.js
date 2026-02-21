/**
 * DRP Collector extension - content script.
 *
 * On launcher page: store drpid and collectorBase from URL, let redirect proceed.
 * On data.gov pages: inject "Save as PDF" button; on click, generate PDF and POST to collector.
 *
 * Content scripts run in an isolated world and cannot see page globals like window.html2pdf.
 * We inject a script into the page context to run html2pdf, then receive the blob via custom event.
 */
(function () {
  "use strict";

  const LAUNCHER_MATCH = /\/extension\/launcher/;
  const DRP_ID = "drp-collector-save-btn";

  function isLauncherPage() {
    return LAUNCHER_MATCH.test(window.location.pathname);
  }

  function handleLauncherPage() {
    const params = new URLSearchParams(window.location.search);
    const drpid = params.get("drpid");
    const url = params.get("url");
    const collectorBase = window.location.origin;
    if (drpid && url) {
      chrome.storage.local.set({ drpid, collectorBase }).catch(() => {});
    }
  }

  function injectPageScript() {
    const s = document.createElement("script");
    s.src = chrome.runtime.getURL("page.js");
    (document.head || document.documentElement).appendChild(s);
  }

  function createPdfBlob(collectorBase) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        document.removeEventListener("drp-pdf-ready", onReady);
        document.removeEventListener("drp-pdf-error", onErr);
        reject(new Error("PDF generation timed out (html2pdf may still be loading)"));
      }, 60000);
      const onReady = (e) => {
        clearTimeout(timeout);
        document.removeEventListener("drp-pdf-ready", onReady);
        document.removeEventListener("drp-pdf-error", onErr);
        resolve(e.detail);
      };
      const onErr = (e) => {
        clearTimeout(timeout);
        document.removeEventListener("drp-pdf-ready", onReady);
        document.removeEventListener("drp-pdf-error", onErr);
        reject(new Error(e.detail || "PDF generation failed"));
      };
      document.addEventListener("drp-pdf-ready", onReady);
      document.addEventListener("drp-pdf-error", onErr);
      document.dispatchEvent(new CustomEvent("drp-generate-pdf", { detail: { collectorBase } }));
    });
  }

  function showToast(msg, isError) {
    const el = document.getElementById(DRP_ID + "-toast");
    if (el) el.remove();
    const toast = document.createElement("div");
    toast.id = DRP_ID + "-toast";
    toast.textContent = msg;
    toast.style.cssText =
      "position:fixed;bottom:80px;right:20px;padding:10px 16px;background:" +
      (isError ? "#c44" : "#282") +
      ";color:#fff;border-radius:6px;z-index:2147483647;font-size:14px;";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
  }

  function addSaveButton() {
    if (document.getElementById(DRP_ID)) return;

    injectPageScript();

    const btn = document.createElement("button");
    btn.id = DRP_ID;
    btn.textContent = "Save as PDF";
    btn.className = "drp-collector-btn";
    document.body.appendChild(btn);

    btn.addEventListener("click", async () => {
      var stored;
      try {
        stored = await chrome.storage.local.get(["drpid", "collectorBase"]);
      } catch (e) {
        if (e && e.message && String(e.message).indexOf("invalidated") !== -1) {
          showToast("Extension was reloaded. Refresh this page and use Copy & Open again.", true);
          return;
        }
        throw e;
      }
      var drpid = stored.drpid, collectorBase = stored.collectorBase;
      if (!drpid || !collectorBase) {
        showToast("Use Copy & Open from collector first.", true);
        return;
      }

      btn.disabled = true;
      btn.textContent = "Saving...";
      try {
        const pdfBase64 = await createPdfBlob(collectorBase);
        if (!pdfBase64 || typeof pdfBase64 !== "string") {
          showToast("No PDF data received", true);
          return;
        }
        const resp = await chrome.runtime.sendMessage({
          type: "drp-save-pdf",
          collectorBase,
          drpid,
          url: window.location.href,
          referrer: document.referrer || "",
          pdfBase64,
        });
        if (resp && resp.ok) {
          showToast("Saved: " + (resp.filename || "OK"), false);
        } else {
          showToast((resp && resp.error) || "Save failed", true);
        }
      } catch (e) {
        var msg = e && e.message ? String(e.message) : "Failed to save";
        if (msg.indexOf("invalidated") !== -1) {
          msg = "Extension was reloaded. Refresh this page and use Copy & Open again.";
        }
        showToast(msg, true);
      } finally {
        btn.disabled = false;
        btn.textContent = "Save as PDF";
      }
    });
  }

  if (isLauncherPage()) {
    handleLauncherPage();
  } else {
    addSaveButton();
  }
})();
