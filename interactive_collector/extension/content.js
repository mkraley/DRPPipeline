/**
 * DRP Collector extension - content script.
 *
 * On launcher page: store drpid and collectorBase from URL, let redirect proceed.
 * On other pages: show "Save as PDF" when the collector's downloads watcher is on
 * (same as Copy & Open). When Save is pressed in the collector, watcher turns off
 * and we hide the button (via polling).
 */
(function () {
  "use strict";

  const LAUNCHER_MATCH = /\/extension\/launcher/;
  const DRP_ID = "drp-collector-save-btn";
  const WATCHER_POLL_MS = 25000;
  var pageScriptInjected = false;
  var watcherPollTimer = null;

  function isLauncherPage() {
    return LAUNCHER_MATCH.test(window.location.pathname);
  }

  function handleLauncherPage() {
    try {
      if (!chrome.runtime || !chrome.runtime.id) return;
    } catch (e) {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const drpid = params.get("drpid");
    const url = params.get("url");
    const collectorBase = window.location.origin;
    if (drpid && url) {
      chrome.storage.local.set({ drpid, collectorBase }).then(
        function () {
          window.location.href = url;
        },
        function () {
          window.location.href = url;
        }
      );
    }
  }

  function clearWatcherPoll() {
    if (watcherPollTimer) {
      clearInterval(watcherPollTimer);
      watcherPollTimer = null;
    }
  }

  function isContextInvalidated(err) {
    var msg = err && (err.message || String(err));
    return typeof msg === "string" && msg.indexOf("Extension context invalidated") !== -1;
  }

  function checkWatcherAndShowOrHide() {
    try {
      if (!chrome.runtime || !chrome.runtime.id) return;
    } catch (e) {
      return;
    }
    chrome.storage.local.get(["drpid", "collectorBase"]).then(
      function (stored) {
        var drpid = stored.drpid, collectorBase = stored.collectorBase;
        if (!drpid || !collectorBase) {
          removeCollectorButtons();
          clearWatcherPoll();
          return;
        }
        addSaveButton();
        startWatcherPoll(collectorBase);
      },
      function (e) {
        if (isContextInvalidated(e)) {
          clearWatcherPoll();
          removeCollectorButtons();
        }
      }
    );
  }

  function startWatcherPoll(collectorBase) {
    clearWatcherPoll();
    watcherPollTimer = setInterval(function () {
      try {
        if (!chrome.runtime || !chrome.runtime.id) {
          clearWatcherPoll();
          removeCollectorButtons();
          return;
        }
      } catch (e) {
        clearWatcherPoll();
        removeCollectorButtons();
        return;
      }
      chrome.runtime.sendMessage({ type: "drp-watcher-status", collectorBase })
        .then(function (res) {
          if (res && res.watching) return;
          try {
            chrome.storage.local.remove(["drpid", "collectorBase"]).catch(function () {});
          } catch (_) {}
          removeCollectorButtons();
          clearWatcherPoll();
        })
        .catch(function (e) {
          if (isContextInvalidated(e)) {
            clearWatcherPoll();
            removeCollectorButtons();
          }
        });
    }, WATCHER_POLL_MS);
  }

  function removeCollectorButtons() {
    var btn = document.getElementById(DRP_ID);
    if (btn) btn.remove();
  }

  function injectPageScript() {
    if (pageScriptInjected) return;
    pageScriptInjected = true;
    const s = document.createElement("script");
    s.src = chrome.runtime.getURL("page.js");
    (document.head || document.documentElement).appendChild(s);
  }

  function createPdfBlob(collectorBase) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        document.removeEventListener("drp-pdf-ready", onReady);
        document.removeEventListener("drp-pdf-error", onErr);
        reject(new Error("PDF generation timed out (try a shorter page)"));
      }, 300000);
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
      "position:fixed;bottom:80px;right:20px;padding:12px 18px;background:" +
      (isError ? "#c44" : "#282") +
      ";color:#fff;border-radius:6px;z-index:2147483647;font-size:14px;max-width:90vw;";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), isError ? 6000 : 5000);
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
      showToast("Generating PDF...", false);
      try {
        var res = await chrome.runtime.sendMessage({
          type: "drp-print-to-pdf",
          collectorBase,
          drpid,
          url: window.location.href,
          referrer: (document.referrer || "").trim() || "",
          title: (document.title || "").trim() || "",
        });
        if (res && res.ok) {
          showToast("Saved: " + (res.filename || "OK"), false);
          return;
        }
        if (res && res.fallback) {
          showToast("Using alternative PDF method...", false);
          const pdfBase64 = await createPdfBlob(collectorBase);
          if (!pdfBase64 || typeof pdfBase64 !== "string") {
            showToast("No PDF data received", true);
            return;
          }
          var r2 = await chrome.runtime.sendMessage({
            type: "drp-save-pdf",
            collectorBase,
            drpid,
            url: window.location.href,
            referrer: (document.referrer || "").trim() || "",
            pdfBase64,
            title: (document.title || "").trim() || "",
          });
          if (r2 && r2.ok) {
            showToast("Saved: " + (r2.filename || "OK"), false);
          } else {
            showToast((r2 && r2.error) || "Save failed", true);
          }
          return;
        }
        showToast((res && res.error) || "Print to PDF failed", true);
        return;
      } catch (e) {
        var msg = e && e.message ? String(e.message) : "Failed to save";
        if (msg.indexOf("invalidated") !== -1) {
          showToast("Extension was reloaded. Refresh this page and use Copy & Open again.", true);
        } else {
          try {
            showToast("Using alternative PDF method...", false);
            const pdfBase64 = await createPdfBlob(collectorBase);
            if (pdfBase64 && typeof pdfBase64 === "string") {
              var r2 = await chrome.runtime.sendMessage({
                type: "drp-save-pdf",
                collectorBase,
                drpid,
                url: window.location.href,
                referrer: (document.referrer || "").trim() || "",
                pdfBase64,
                title: (document.title || "").trim() || "",
              });
              if (r2 && r2.ok) {
                showToast("Saved: " + (r2.filename || "OK"), false);
                return;
              }
            }
          } catch (_) {}
          showToast(msg, true);
        }
      } finally {
        btn.disabled = false;
        btn.textContent = "Save as PDF";
      }
    });
  }

  function ensureButtons() {
    if (document.getElementById(DRP_ID)) return;
    try {
      checkWatcherAndShowOrHide();
    } catch (e) {
      if (isContextInvalidated(e)) {
        clearWatcherPoll();
        removeCollectorButtons();
      }
    }
  }

  function onUrlChange() {
    if (isLauncherPage()) return;
    setTimeout(ensureButtons, 150);
  }

  if (isLauncherPage()) {
    handleLauncherPage();
  } else {
    try {
      checkWatcherAndShowOrHide();
    } catch (e) {
      if (isContextInvalidated(e)) {
        clearWatcherPoll();
        removeCollectorButtons();
      }
    }
    window.addEventListener("popstate", onUrlChange);
    var _push = history.pushState, _replace = history.replaceState;
    history.pushState = function () {
      _push.apply(this, arguments);
      onUrlChange();
    };
    history.replaceState = function () {
      _replace.apply(this, arguments);
      onUrlChange();
    };
  }
})();
