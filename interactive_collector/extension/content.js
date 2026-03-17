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
  var DRP_META_DEBUG = true;
  function drpLog() {
    if (DRP_META_DEBUG && typeof console !== "undefined" && console.log) {
      console.log.apply(console, ["[DRP meta]"].concat(Array.prototype.slice.call(arguments)));
    }
  }

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
      chrome.storage.local.set({ drpid, collectorBase, sourcePageUrl: url, allowSameHostMetadataOnce: true }).then(
        function () {
          window.location.href = url;
        },
        function () {
          window.location.href = url;
        }
      );
    }
  }

  function urlOriginAndPath(u) {
    if (!u) return "";
    try {
      var a = document.createElement("a");
      a.href = u;
      var path = (a.pathname || "/").replace(/\/+$/, "") || "/";
      return (a.host || a.hostname) + path;
    } catch (e) {
      return u;
    }
  }

  function isCmsDomain() {
    try {
      return (window.location.hostname || "").indexOf("data.cms.gov") !== -1;
    } catch (e) {
      return false;
    }
  }

  function getElementText(el) {
    if (!el) return "";
    var t = (el.innerText != null && el.innerText !== "") ? el.innerText : (el.textContent || "");
    return (t && typeof t === "string") ? t.trim() : "";
  }
  function getElementHtml(el) {
    if (!el) return "";
    var h = (el.innerHTML != null) ? el.innerHTML : "";
    return (h && typeof h === "string") ? h.trim() : "";
  }

  function extractMetadataFromPage() {
    var meta = {};
    var el;
    var isCms = isCmsDomain();
    var doc = document;

    if (isCms) {
      // data.cms.gov selectors (SPA; often need delay before extract)
      el = doc.querySelector("h1");
      if (el) {
        var titleText = getElementText(el);
        if (titleText && titleText.length > 2 && titleText.toLowerCase() !== "loading") meta.title = titleText;
      }
      el = doc.querySelector("div.DatasetPage__summary-field-summary-container") ||
           doc.querySelector("div[class*='DatasetPage__summary']");
      if (el) {
        var summaryHtml = getElementHtml(el);
        var summaryText = getElementText(el);
        meta.summary = (summaryHtml && summaryHtml.length > 0) ? summaryHtml : (summaryText ? "<p>" + summaryText + "</p>" : "");
      }
      el = doc.querySelector("ul.DatasetDetails__tags") ||
           doc.querySelector("ul[class*='DatasetDetails__tags']") ||
           doc.querySelector("div.DatasetDetails__tags") ||
           doc.querySelector("div[class*='DatasetDetails__tags']");
      if (el) {
        var tagEls = el.querySelectorAll("a");
        if (tagEls.length) {
          meta.keywords = Array.prototype.map.call(tagEls, function (n) { return getElementText(n); }).filter(Boolean).join("; ");
        }
        if (!meta.keywords) meta.keywords = getElementText(el);
      }
      // Agency: div.DatasetHero__meta with <span>Data source</span> and sibling <span>agency name</span>
      var metaDivs = doc.querySelectorAll("div.DatasetHero__meta, div[class*='DatasetHero__meta']");
      for (var d = 0; d < metaDivs.length; d++) {
        var spans = metaDivs[d].querySelectorAll("span");
        for (var s = 0; s < spans.length; s++) {
          if (getElementText(spans[s]).toLowerCase().indexOf("data source") !== -1 && spans[s].nextElementSibling) {
            meta.agency = getElementText(spans[s].nextElementSibling);
            break;
          }
        }
        if (meta.agency) break;
      }
    }

    if (!meta.title) {
      el = doc.querySelector('h1[itemprop="name"]');
      if (el) meta.title = getElementText(el);
    }
    if (!meta.title) {
      el = doc.querySelector("h2.asset-name");
      if (el) meta.title = getElementText(el);
    }
    if (!meta.title && doc.title) meta.title = doc.title.trim();

    if (!meta.summary) {
      el = doc.querySelector("div.description-section");
      if (el) meta.summary = getElementHtml(el) || ("<p>" + getElementText(el) + "</p>");
    }
    if (!meta.summary) {
      el = doc.querySelector('div[itemprop="description"]');
      if (el) meta.summary = getElementHtml(el) || ("<p>" + getElementText(el) + "</p>");
    }

    if (!meta.keywords) {
      var tagsSection = doc.querySelector("section.tags");
      if (tagsSection) {
        var tagEls = tagsSection.querySelectorAll("a");
        if (tagEls.length) {
          meta.keywords = Array.prototype.map.call(tagEls, function (n) { return getElementText(n); }).filter(Boolean).join("; ");
        }
        if (!meta.keywords) meta.keywords = getElementText(tagsSection);
      }
    }
    if (!meta.keywords) {
      var kwNodes = doc.querySelectorAll('[itemprop="keywords"]');
      if (kwNodes.length) {
        meta.keywords = Array.prototype.map.call(kwNodes, function (n) { return getElementText(n); }).filter(Boolean).join("; ");
      }
    }

    if (!meta.agency) {
      el = doc.querySelector('[itemprop="publisher"]');
      if (el) {
        var name = el.getAttribute("content") || getElementText(el.querySelector("[itemprop='name']")) || getElementText(el);
        if (name) meta.agency = name.trim();
      }
    }
    if (!meta.office) {
      el = doc.querySelector(".dataset-office, [data-field='organization'] .value, .publisher-name");
      if (el) meta.office = getElementText(el);
    }
    if (!meta.office && meta.agency) meta.office = meta.agency;

    var today = new Date();
    meta.download_date = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
    drpLog("extract result", {
      title: meta.title ? meta.title.substring(0, 50) + (meta.title.length > 50 ? "..." : "") : null,
      summaryLen: meta.summary ? meta.summary.length : 0,
      keywords: meta.keywords ? meta.keywords.substring(0, 40) + "..." : null,
      agency: meta.agency || null
    });
    return meta;
  }

  function urlHost(u) {
    if (!u) return "";
    try {
      var a = document.createElement("a");
      a.href = u;
      return (a.hostname || a.host || "").toLowerCase();
    } catch (e) { return ""; }
  }

  function doSendMetadataFromPage(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce) {
    drpLog("doSendMetadataFromPage", { collectorBase: collectorBase, drpid: drpid, sourcePageUrl: sourcePageUrl });
    if (!sourcePageUrl) {
      drpLog("bail: no sourcePageUrl");
      return;
    }
    var currentKey = urlOriginAndPath(window.location.href);
    var sourceKey = urlOriginAndPath(sourcePageUrl);
    var exactMatch = currentKey === sourceKey;
    var currentHost = urlHost(window.location.href);
    var sourceHost = urlHost(sourcePageUrl);
    var sameHost = currentHost && sourceHost && currentHost === sourceHost;
    var allowSend = exactMatch || (sameHost && allowSameHostMetadataOnce);
    drpLog("URL check", { currentKey: currentKey, sourceKey: sourceKey, exactMatch: exactMatch, sameHost: sameHost, allowSameHostOnce: !!allowSameHostMetadataOnce, allowSend: allowSend });
    if (!allowSend) {
      drpLog("bail: not source URL and no one-time same-host allowance (or already used)");
      return;
    }
    var meta = extractMetadataFromPage();
    meta.drpid = parseInt(drpid, 10);
    delete meta.office;
    drpLog("extracted meta keys", Object.keys(meta), "title?", !!meta.title, "summary?", !!meta.summary);
    if (Object.keys(meta).length <= 1) {
      drpLog("bail: too few keys (will not POST)");
      return;
    }
    chrome.runtime.sendMessage(
      { type: "drp-metadata-from-page", collectorBase: collectorBase, payload: meta },
      function (response) {
        drpLog("POST response", response);
        if (response && response.ok) {
          chrome.storage.local.remove(["sourcePageUrl", "allowSameHostMetadataOnce"]).catch(function () {});
        }
      }
    );
  }

  function cmsContentReady() {
    var h1 = document.querySelector("h1");
    var titleText = h1 ? getElementText(h1) : "";
    if (titleText && titleText.length > 2 && titleText.toLowerCase() !== "loading") return true;
    var summaryEl = document.querySelector("div.DatasetPage__summary-field-summary-container") ||
                    document.querySelector("div[class*='DatasetPage__summary']");
    if (summaryEl && (getElementHtml(summaryEl).length > 0 || getElementText(summaryEl).length > 0)) return true;
    return false;
  }

  function sendMetadataFromPageIfSource(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce) {
    drpLog("sendMetadataFromPageIfSource", { isCms: isCmsDomain() });
    if (!collectorBase || !drpid || !sourcePageUrl) {
      drpLog("bail: missing collectorBase, drpid, or sourcePageUrl");
      return;
    }
    if (isCmsDomain()) {
      drpLog("CMS: starting wait-for-content then extract");
      var delays = [3000, 6000, 10000];
      var attempt = 0;
      var pollMs = 400;
      var pollMax = 12000;
      var pollStart = Date.now();
      function waitThenExtract() {
        var ready = cmsContentReady();
        var elapsed = Date.now() - pollStart;
        if (elapsed >= pollMax) drpLog("CMS: content wait timeout after " + (pollMax / 1000) + "s, extracting anyway");
        if (ready) drpLog("CMS: content ready after " + (elapsed / 1000).toFixed(1) + "s");
        if (ready || elapsed >= pollMax) {
          tryExtract();
          return;
        }
        setTimeout(waitThenExtract, pollMs);
      }
      function tryExtract() {
        var m = extractMetadataFromPage();
        drpLog("CMS tryExtract attempt " + (attempt + 1), "title?", !!m.title, "summary?", !!m.summary);
        if (m.title || m.summary) {
          drpLog("CMS: got title or summary, sending");
          doSendMetadataFromPage(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce);
          return;
        }
        attempt++;
        if (attempt < delays.length) {
          var nextMs = attempt === 1 ? 3000 : (delays[attempt] - delays[attempt - 1]);
          drpLog("CMS: retry in " + (nextMs / 1000) + "s");
          setTimeout(tryExtract, nextMs);
        } else {
          drpLog("CMS: no more retries, sending what we have");
          doSendMetadataFromPage(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce);
        }
      }
      setTimeout(waitThenExtract, 500);
      return;
    }
    doSendMetadataFromPage(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce);
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
    chrome.storage.local.get(["drpid", "collectorBase", "sourcePageUrl", "allowSameHostMetadataOnce"]).then(
      function (stored) {
        var drpid = stored.drpid, collectorBase = stored.collectorBase, sourcePageUrl = stored.sourcePageUrl, allowSameHostMetadataOnce = stored.allowSameHostMetadataOnce;
        drpLog("storage get", { drpid: drpid, collectorBase: collectorBase, sourcePageUrl: sourcePageUrl, allowSameHostOnce: !!allowSameHostMetadataOnce });
        if (!drpid || !collectorBase) {
          drpLog("bail: missing drpid or collectorBase");
          removeCollectorButtons();
          clearWatcherPoll();
          return;
        }
        chrome.runtime.sendMessage({ type: "drp-watcher-status", collectorBase: collectorBase }).then(
          function (res) {
            if (!res || !res.watching) {
              drpLog("watcher not active – hide button and clear storage");
              removeCollectorButtons();
              clearWatcherPoll();
              chrome.storage.local.remove(["drpid", "collectorBase", "sourcePageUrl", "allowSameHostMetadataOnce"]).catch(function () {});
              return;
            }
            if (!sourcePageUrl) drpLog("no sourcePageUrl – metadata preload will not run");
            if (!isLauncherPage()) {
              sendMetadataFromPageIfSource(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce);
            } else {
              drpLog("on launcher page – skip metadata preload until redirect to target");
            }
            addSaveButton();
            startWatcherPoll(collectorBase);
          },
          function () {
            removeCollectorButtons();
            clearWatcherPoll();
          }
        );
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

  /** Run expansion in the page (read more, show more, accordions), then resolve. Used before print-to-PDF. */
  function runExpandForPdf() {
    return new Promise((resolve) => {
      let readyTimeout;
      let doneTimeout;
      const done = () => {
        document.removeEventListener("drp-expand-done", done);
        document.removeEventListener("drp-expand-ready", onReady);
        clearTimeout(readyTimeout);
        clearTimeout(doneTimeout);
        resolve();
      };
      const onReady = () => {
        document.removeEventListener("drp-expand-ready", onReady);
        clearTimeout(readyTimeout);
        document.addEventListener("drp-expand-done", done);
        document.dispatchEvent(new CustomEvent("drp-expand-for-pdf"));
        doneTimeout = setTimeout(done, 60000);
      };
      document.addEventListener("drp-expand-ready", onReady);
      readyTimeout = setTimeout(() => {
        document.removeEventListener("drp-expand-ready", onReady);
        document.addEventListener("drp-expand-done", done);
        document.dispatchEvent(new CustomEvent("drp-expand-for-pdf"));
        doneTimeout = setTimeout(done, 60000);
      }, 5000);
    });
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
      try {
        console.log("[DRP] In-page PDF: waiting for page script...");
      } catch (e) {}
      let dispatched = false;
      const onPageReady = () => {
        if (dispatched) return;
        dispatched = true;
        document.removeEventListener("drp-page-ready", onPageReady);
        clearTimeout(pageReadyTimeout);
        try {
          console.log("[DRP] In-page PDF: dispatching drp-generate-pdf (expansion will run; look for [DRP expand] in console)");
        } catch (e) {}
        document.dispatchEvent(new CustomEvent("drp-generate-pdf", { detail: { collectorBase } }));
      };
      document.addEventListener("drp-page-ready", onPageReady);
      const pageReadyTimeout = setTimeout(() => {
        if (dispatched) return;
        dispatched = true;
        document.removeEventListener("drp-page-ready", onPageReady);
        try {
          console.log("[DRP] In-page PDF: page script not ready in 15s, dispatching anyway");
        } catch (e) {}
        document.dispatchEvent(new CustomEvent("drp-generate-pdf", { detail: { collectorBase } }));
      }, 15000);
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
      showToast("Expanding content...", false);
      try {
        console.log("[DRP] Save as PDF clicked");
        injectPageScript();
        await runExpandForPdf();
        showToast("Generating PDF...", false);
        var res = await chrome.runtime.sendMessage({
          type: "drp-print-to-pdf",
          collectorBase,
          drpid,
          url: window.location.href,
          referrer: (document.referrer || "").trim() || "",
          title: (document.title || "").trim() || "",
        });
        if (res && res.ok) {
          console.log("[DRP] PDF saved via print (page was expanded first)");
          showToast("Saved: " + (res.filename || "OK"), false);
          return;
        }
        if (res && res.fallback) {
          console.log("[DRP] Using in-page PDF (expansion will run)");
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

  function isPdfLink(href) {
    if (!href || typeof href !== "string") return false;
    try {
      var a = document.createElement("a");
      a.href = href;
      var path = (a.pathname || "").toLowerCase();
      return path.endsWith(".pdf") || /\.pdf(\?|#|$)/i.test(a.href);
    } catch (e) { return false; }
  }

  document.addEventListener("click", function (e) {
    var anchor = e.target && e.target.closest ? e.target.closest("a[href]") : null;
    if (!anchor || !anchor.href) return;
    if (!isPdfLink(anchor.href)) return;
    chrome.runtime.sendMessage({
      type: "drp-fetch-pdf-to-project",
      pdfUrl: anchor.href,
      referrer: window.location.href,
      pageTitle: (anchor.textContent || "").trim().substring(0, 80) || null,
    }).catch(function () {});
  }, true);

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
