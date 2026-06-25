/**
 * DRP Collector extension - content script.
 *
 * On launcher page: store drpid and collectorBase from URL, let redirect proceed.
 * On other pages: show "Save as Markdown" and "Save as PDF" when the collector's
 * downloads watcher is on
 * (same as Copy & Open). When Save is pressed in the collector, watcher turns off
 * and we hide the button (via polling).
 */
(function () {
  "use strict";

  const LAUNCHER_MATCH = /\/extension\/launcher/;
  const DRP_ID = "drp-collector-save-btn";
  const DRP_MD_ID = "drp-collector-save-md-btn";
  const WATCHER_POLL_MS = 25000;
  var pageScriptInjected = false;
  var pageScriptReady = false;
  var pageScriptReadyPromise = null;
  var watcherPollTimer = null;

  /** Load page.js (~30KB) and wait until expansion handlers are registered. PDF libs load separately on fallback only. */
  function ensurePageScriptReady() {
    if (pageScriptReady) return Promise.resolve();
    if (pageScriptReadyPromise) return pageScriptReadyPromise;
    pageScriptReadyPromise = new Promise(function (resolve, reject) {
      function onReady() {
        document.removeEventListener("drp-expand-ready", onReady);
        clearTimeout(timeoutId);
        pageScriptReady = true;
        resolve();
      }
      document.addEventListener("drp-expand-ready", onReady);
      var timeoutId = setTimeout(function () {
        document.removeEventListener("drp-expand-ready", onReady);
        pageScriptReadyPromise = null;
        reject(new Error("Expansion script timed out"));
      }, 15000);
      if (!pageScriptInjected) {
        pageScriptInjected = true;
        var s = document.createElement("script");
        s.src = chrome.runtime.getURL("page.js");
        s.onerror = function () {
          clearTimeout(timeoutId);
          document.removeEventListener("drp-expand-ready", onReady);
          pageScriptInjected = false;
          pageScriptReadyPromise = null;
          reject(new Error("Failed to load expansion script"));
        };
        (document.head || document.documentElement).appendChild(s);
      } else {
        document.dispatchEvent(new CustomEvent("drp-expand-ping"));
      }
    });
    return pageScriptReadyPromise;
  }

  function injectPageScript() {
    return ensurePageScriptReady();
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

  function extractMetadataFromPage(options) {
    var allowDocumentTitle = !options || options.allowDocumentTitle !== false;
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
    if (!meta.title && allowDocumentTitle && doc.title) meta.title = doc.title.trim();

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
    return meta;
  }

  /** Title from on-page metadata fields (not the HTML document title). */
  function metadataTitleFromPage() {
    return (extractMetadataFromPage({ allowDocumentTitle: false }).title || "").trim();
  }

  function titleForSavedPage(sourcePageUrl) {
    if (sourcePageUrl) {
      var currentKey = urlOriginAndPath(window.location.href);
      var sourceKey = urlOriginAndPath(sourcePageUrl);
      if (currentKey === sourceKey) {
        var fieldTitle = metadataTitleFromPage();
        if (fieldTitle) {
          return fieldTitle;
        }
      }
    }
    return (document.title || "").trim() || "";
  }

  function isAgDataCommonsHost() {
    return urlHost(window.location.href).indexOf("agdatacommons.nal.usda.gov") !== -1;
  }

  function isSourceCatalogPage(sourcePageUrl) {
    if (!sourcePageUrl) return false;
    return urlOriginAndPath(window.location.href) === urlOriginAndPath(sourcePageUrl);
  }

  /** When saving the ADC source item page, use the batch collector catalog PDF name. */
  function filenameForSavedPdf(sourcePageUrl) {
    if (isAgDataCommonsHost() && isSourceCatalogPage(sourcePageUrl)) {
      return "catalog_detail.pdf";
    }
    return "";
  }

  function dismissAgDataCommonsCookiesInContentScript() {
    if (!isAgDataCommonsHost()) return false;
    var labels = ["Accept all", "Accept All", "I agree"];
    var buttons = document.querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) {
      var text = (buttons[i].textContent || "").replace(/[\s\u00a0]+/g, " ").trim();
      for (var j = 0; j < labels.length; j++) {
        if (text === labels[j]) {
          try {
            buttons[i].click();
            return true;
          } catch (e) {}
        }
      }
    }
    return false;
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
    if (!sourcePageUrl) {
      return;
    }
    var currentKey = urlOriginAndPath(window.location.href);
    var sourceKey = urlOriginAndPath(sourcePageUrl);
    var exactMatch = currentKey === sourceKey;
    var currentHost = urlHost(window.location.href);
    var sourceHost = urlHost(sourcePageUrl);
    var sameHost = currentHost && sourceHost && currentHost === sourceHost;
    var allowSend = exactMatch || (sameHost && allowSameHostMetadataOnce);
    if (!allowSend) {
      return;
    }
    var meta = extractMetadataFromPage();
    meta.drpid = parseInt(drpid, 10);
    delete meta.office;
    if (Object.keys(meta).length <= 1) {
      return;
    }
    chrome.runtime.sendMessage(
      { type: "drp-metadata-from-page", collectorBase: collectorBase, payload: meta },
      function (response) {
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
    if (!collectorBase || !drpid || !sourcePageUrl) {
      return;
    }
    if (isCmsDomain()) {
      var delays = [3000, 6000, 10000];
      var attempt = 0;
      var pollMs = 400;
      var pollMax = 12000;
      var pollStart = Date.now();
      function waitThenExtract() {
        var ready = cmsContentReady();
        var elapsed = Date.now() - pollStart;
        if (ready || elapsed >= pollMax) {
          tryExtract();
          return;
        }
        setTimeout(waitThenExtract, pollMs);
      }
      function tryExtract() {
        var m = extractMetadataFromPage();
        if (m.title || m.summary) {
          doSendMetadataFromPage(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce);
          return;
        }
        attempt++;
        if (attempt < delays.length) {
          var nextMs = attempt === 1 ? 3000 : (delays[attempt] - delays[attempt - 1]);
          setTimeout(tryExtract, nextMs);
        } else {
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
        if (!drpid || !collectorBase) {
          removeCollectorButtons();
          clearWatcherPoll();
          return;
        }
        chrome.runtime.sendMessage({ type: "drp-watcher-status", collectorBase: collectorBase }).then(
          function (res) {
            if (!res || !res.watching) {
              removeCollectorButtons();
              clearWatcherPoll();
              chrome.storage.local.remove(["drpid", "collectorBase", "sourcePageUrl", "allowSameHostMetadataOnce"]).catch(function () {});
              return;
            }
            if (!isLauncherPage()) {
              sendMetadataFromPageIfSource(collectorBase, drpid, sourcePageUrl, allowSameHostMetadataOnce);
            }
            addSaveButtons();
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
    var pdfBtn = document.getElementById(DRP_ID);
    if (pdfBtn) pdfBtn.remove();
    var mdBtn = document.getElementById(DRP_MD_ID);
    if (mdBtn) mdBtn.remove();
  }

  /**
   * Prefer main/article content so chrome, nav, and extension UI are omitted when possible.
   */
  function extractMainHtmlForMarkdown() {
    var selectors = [
      "main",
      'article[role="main"]',
      "article",
      '[role="main"]',
      "#main-content",
      "#content",
      ".region-content",
    ];
    var i;
    var el;
    var txt;
    for (i = 0; i < selectors.length; i++) {
      el = document.querySelector(selectors[i]);
      if (el) {
        txt = getElementText(el);
        if (txt && txt.length >= 80) {
          return el.outerHTML;
        }
      }
    }
    el = document.body;
    if (!el) {
      return document.documentElement ? document.documentElement.outerHTML : "";
    }
    var clone = el.cloneNode(true);
    var rm = clone.querySelectorAll(
      "#drp-collector-save-btn, #drp-collector-save-md-btn, #drp-collector-save-btn-toast"
    );
    for (i = 0; i < rm.length; i++) {
      rm[i].remove();
    }
    return clone.innerHTML;
  }

  async function postMarkdownToCollector(collectorBase, drpid, url, referrer, title, html) {
    var base = (collectorBase || "").replace(/\/$/, "");
    var fd = new FormData();
    fd.append("drpid", String(drpid));
    fd.append("url", url);
    fd.append("referrer", referrer || "");
    if (title) fd.append("title", title);
    fd.append("html", html);
    var r = await fetch(base + "/api/extension/save-markdown", { method: "POST", body: fd });
    var data = {};
    try {
      data = await r.json();
    } catch (e) {
      data = {};
    }
    if (!r.ok) {
      throw new Error((data && data.error) || "HTTP " + r.status);
    }
    if (!data.ok) {
      throw new Error((data && data.error) || "Save failed");
    }
    return data;
  }

  /**
   * Clicks that must run in the *content-script* world on the same synchronous turn as the
   * user's Save click. After `await chrome.storage…` or `await runExpandForPdf()`, user
   * activation is gone and React/DOL may ignore clicks dispatched from injected page.js.
   * DOL: <a class="showMore" id="showMore" tabindex="0">+Show all data fields</a>
   * EDI: <div class="pasta-more pasta-more-show"></div>
   */
  function trustedClicksForPdfExpansion() {
    function labelLooksLikeShowAllDataFields(el) {
      var raw = ((el.getAttribute && el.getAttribute("aria-label")) || "") + " " + (el.textContent || "");
      var t = raw.replace(/[\s\u00a0]+/g, " ").trim().replace(/^[\+\uFF0B\s]+/, "");
      return /show\s+all|all\s+data\s+fields?|data\s+fields?/i.test(t);
    }
    function tryClick(el) {
      if (!el || typeof el.click !== "function") return;
      if (!labelLooksLikeShowAllDataFields(el)) return;
      try {
        el.scrollIntoView({ block: "nearest", behavior: "auto" });
      } catch (e) {}
      try {
        if (el.focus) el.focus();
      } catch (e) {}
      try {
        el.click();
      } catch (e) {}
    }
    function tryClickPastaMore(el) {
      if (!el || typeof el.click !== "function") return;
      try {
        el.scrollIntoView({ block: "nearest", behavior: "auto" });
      } catch (e) {}
      try {
        el.click();
      } catch (e) {}
    }
    tryClick(document.getElementById("showMore"));
    var links = document.querySelectorAll("a.showMore");
    for (var i = 0; i < links.length; i++) {
      tryClick(links[i]);
    }
    var pastaToggles = document.querySelectorAll(".pasta-more.pasta-more-show");
    for (var p = 0; p < pastaToggles.length; p++) {
      tryClickPastaMore(pastaToggles[p]);
    }
    var moreLinks = document.querySelectorAll("a.morelink, .morelink");
    for (var m = 0; m < moreLinks.length; m++) {
      var ml = moreLinks[m];
      var txt = (ml.textContent || "").replace(/[\s\u00a0]+/g, " ").trim();
      if (!/show\s+more/i.test(txt) || /show\s+less/i.test(txt)) continue;
      tryClickPastaMore(ml);
    }
  }

  /** Unhide EDI/PASTA truncated blocks when click handlers did not run (see page.js twin). */
  function revealPastaMoreFallbackInContentScript() {
    function revealRoot(root) {
      if (!root || !root.querySelectorAll) return;
      var spans = root.querySelectorAll(".morecontent span");
      for (var s = 0; s < spans.length; s++) {
        try {
          spans[s].style.display = "inline";
        } catch (e) {}
      }
      var collapsed = root.querySelectorAll(".pasta-more.pasta-more-show");
      for (var c = 0; c < collapsed.length; c++) {
        var btn = collapsed[c];
        try {
          btn.classList.remove("pasta-more-show");
          btn.classList.add("pasta-more-hide");
        } catch (e2) {}
        try {
          var prev = btn.previousElementSibling;
          while (prev) {
            if (prev.classList) {
              prev.classList.remove("pasta-truncated", "truncated", "ellipsis", "pasta-collapsed", "collapsed");
            }
            try {
              prev.style.maxHeight = "none";
              prev.style.overflow = "visible";
              prev.style.height = "auto";
            } catch (e3) {}
            prev = prev.previousElementSibling;
          }
        } catch (e4) {}
      }
    }
    revealRoot(document);
    var iframes = document.getElementsByTagName("iframe");
    for (var f = 0; f < iframes.length; f++) {
      try {
        var idoc = iframes[f].contentDocument;
        if (idoc) revealRoot(idoc);
      } catch (e5) {}
    }
  }

  /** Unhide panels after #showMore when Drupal/jQuery handlers did not run (see page.js twin). */
  function dolRevealDataFieldsNearShowMoreInContentScript() {
    var sm = document.getElementById("showMore");
    if (!sm) return;
    function reveal(el) {
      if (!el || el.nodeType !== 1) return;
      try {
        el.classList.remove("hidden", "u-hidden", "hide", "d-none");
        el.classList.add("show");
        el.removeAttribute("hidden");
      } catch (e) {}
      try {
        if (el.style && String(el.style.display).toLowerCase() === "none") el.style.display = "block";
        el.style.visibility = "visible";
        el.style.maxHeight = "none";
        el.style.height = "auto";
        el.style.overflow = "visible";
      } catch (e2) {}
    }
    var p = sm.parentElement;
    if (!p) return;
    var after = false;
    for (var i = 0; i < p.children.length; i++) {
      var kid = p.children[i];
      if (kid === sm) {
        after = true;
        continue;
      }
      if (after) reveal(kid);
    }
  }

  /** Run expansion in the page (read more, show more, accordions), then resolve. Used before print-to-PDF. */
  function runExpandForPdf() {
    return ensurePageScriptReady().then(function () {
      return new Promise(function (resolve) {
        var doneTimeout;
        function done() {
          document.removeEventListener("drp-expand-done", done);
          clearTimeout(doneTimeout);
          resolve();
        }
        document.addEventListener("drp-expand-done", done);
        document.dispatchEvent(new CustomEvent("drp-expand-for-pdf"));
        doneTimeout = setTimeout(done, 25000);
      });
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
      let dispatched = false;
      const onPageReady = () => {
        if (dispatched) return;
        dispatched = true;
        document.removeEventListener("drp-page-ready", onPageReady);
        clearTimeout(pageReadyTimeout);
        document.dispatchEvent(new CustomEvent("drp-generate-pdf", { detail: { collectorBase } }));
      };
      document.addEventListener("drp-page-ready", onPageReady);
      const pageReadyTimeout = setTimeout(() => {
        if (dispatched) return;
        dispatched = true;
        document.removeEventListener("drp-page-ready", onPageReady);
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

  function addSaveButtons() {
    if (document.getElementById(DRP_ID) || document.getElementById(DRP_MD_ID)) return;

    ensurePageScriptReady().catch(function () {});

    const mdBtn = document.createElement("button");
    mdBtn.id = DRP_MD_ID;
    mdBtn.textContent = "Save as Markdown";
    mdBtn.className = "drp-collector-btn drp-collector-btn-md";
    mdBtn.title = "Save main page content as Markdown in the project folder";
    document.body.appendChild(mdBtn);

    mdBtn.addEventListener("click", async () => {
      trustedClicksForPdfExpansion();
      var storedMd;
      try {
        storedMd = await chrome.storage.local.get(["drpid", "collectorBase", "sourcePageUrl"]);
      } catch (e) {
        if (e && e.message && String(e.message).indexOf("invalidated") !== -1) {
          showToast("Extension was reloaded. Refresh this page and use Copy & Open again.", true);
          return;
        }
        throw e;
      }
      var drpidMd = storedMd.drpid;
      var collectorBaseMd = storedMd.collectorBase;
      if (!drpidMd || !collectorBaseMd) {
        showToast("Use Copy & Open from collector first.", true);
        return;
      }
      mdBtn.disabled = true;
      mdBtn.textContent = "Saving MD...";
      try {
        injectPageScript();
        await runExpandForPdf();
        dolRevealDataFieldsNearShowMoreInContentScript();
        revealPastaMoreFallbackInContentScript();
        await new Promise(function (r) {
          setTimeout(r, 400);
        });
        var htmlFrag = extractMainHtmlForMarkdown();
        if (!htmlFrag || htmlFrag.length < 20) {
          showToast("Could not read page HTML", true);
          return;
        }
        var dataMd = await postMarkdownToCollector(
          collectorBaseMd,
          drpidMd,
          window.location.href,
          (document.referrer || "").trim() || "",
          titleForSavedPage(storedMd.sourcePageUrl),
          htmlFrag
        );
        var okT = dataMd.table_expand_ok;
        var flT = dataMd.table_expand_fail;
        var tblMsg = "";
        if (typeof okT === "number" || typeof flT === "number") {
          okT = typeof okT === "number" ? okT : 0;
          flT = typeof flT === "number" ? flT : 0;
          if (flT > 0) {
            tblMsg = " (" + okT + " table(s) normalized, " + flT + " skipped)";
          } else if (okT > 0) {
            tblMsg = " (" + okT + " table(s) normalized)";
          }
        }
        showToast("Saved: " + (dataMd.filename || "OK") + tblMsg, false);
      } catch (e) {
        var errMd = e && e.message ? String(e.message) : "Failed to save";
        if (errMd.indexOf("invalidated") !== -1) {
          showToast("Extension was reloaded. Refresh this page and use Copy & Open again.", true);
        } else {
          showToast(errMd, true);
        }
      } finally {
        mdBtn.disabled = false;
        mdBtn.textContent = "Save as Markdown";
      }
    });

    const btn = document.createElement("button");
    btn.id = DRP_ID;
    btn.textContent = "Save as PDF";
    btn.className = "drp-collector-btn";
    btn.title = "Save page as PDF via print (or fallback capture)";
    document.body.appendChild(btn);

    btn.addEventListener("click", async () => {
      trustedClicksForPdfExpansion();
      var stored;
      try {
        stored = await chrome.storage.local.get(["drpid", "collectorBase", "sourcePageUrl"]);
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
      var pdfTitle = titleForSavedPage(stored.sourcePageUrl);
      var pdfFilename = filenameForSavedPdf(stored.sourcePageUrl);
      try {
        injectPageScript();
        dismissAgDataCommonsCookiesInContentScript();
        await runExpandForPdf();
        dolRevealDataFieldsNearShowMoreInContentScript();
        revealPastaMoreFallbackInContentScript();
        await new Promise(function (r) {
          setTimeout(r, 400);
        });
        showToast("Generating PDF...", false);
        var res = await chrome.runtime.sendMessage({
          type: "drp-print-to-pdf",
          collectorBase,
          drpid,
          url: window.location.href,
          referrer: (document.referrer || "").trim() || "",
          title: pdfTitle,
          filename: pdfFilename,
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
            title: pdfTitle,
            filename: pdfFilename,
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
                title: pdfTitle,
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
    if (document.getElementById(DRP_ID) || document.getElementById(DRP_MD_ID)) return;
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
