/**
 * Runs in page context (injected via script src). Loads html2pdf, html2canvas, jsPDF
 * and listens for drp-generate-pdf; generates PDF (chunked for long pages to avoid
 * canvas size limits), converts to base64, dispatches drp-pdf-ready.
 * Before capture, expands "read more", "Show more", accordions (Socrata + CMS),
 * EDI/PASTA ".pasta-more" toggles, and dataset toggles such as "+ Show Full Description"
 * / "Show all data fields".
 */
(function () {
  var base = document.currentScript.src.replace(/\/[^/]*$/, "/");
  var CHUNK_HEIGHT = 6000;
  var MAX_HEIGHT_SINGLE = 7000;

  function wait(ms) {
    return new Promise(function (r) {
      setTimeout(r, ms);
    });
  }

  /**
   * Expand hidden content so it is included in PDF.
   * - Socrata: forge-button.collapse-button ("Read more")
   * - CMS: .ShowMoreContainer button ("Show more (15)") - loop until no more
   * - EDI: .pasta-more.pasta-more-show and .morelink (jQuery show-more/less)
   * - CMS: accordions - expand one at a time, re-query after each (Bootstrap/React)
   * Returns { readMore, showMore, accordions } counts.
   */
  /**
   * Ag Data Commons / Figshare: dismiss cookie banner and expand scroll containers for print.
   */
  function expandForAgDataCommons() {
    var host = (location.hostname || "").toLowerCase();
    if (host.indexOf("agdatacommons.nal.usda.gov") === -1) return;
    try {
      document.querySelectorAll("button").forEach(function (btn) {
        var text = (btn.textContent || "").replace(/[\s\u00a0]+/g, " ").trim().toLowerCase();
        if (text === "accept all" || text === "i agree") {
          try {
            btn.click();
          } catch (_) {}
        }
      });
      document
        .querySelectorAll('[role="dialog"], [aria-labelledby="dialog-cookie-banner-title"]')
        .forEach(function (node) {
          var blob = (node.textContent || "").slice(0, 4000).toLowerCase();
          if (/cookie consent|this website uses cookies/.test(blob)) {
            node.remove();
          }
        });
      document.querySelectorAll("body *").forEach(function (el) {
        if (!el || el.nodeType !== 1) return;
        var style = window.getComputedStyle(el);
        var oy = style.overflowY;
        var o = style.overflow;
        if (oy === "auto" || oy === "scroll" || o === "auto" || o === "scroll") {
          try {
            el.style.overflow = "visible";
            el.style.overflowY = "visible";
            el.style.maxHeight = "none";
            el.style.height = "auto";
          } catch (_) {}
        }
      });
    } catch (_) {}
  }

  function expandForPdf() {
    var readMore = 0, showMore = 0, accordions = 0, fullDescription = 0, dataFields = 0, collapsePanels = 0, pastaMore = 0;
    var clickedOnceForPdf = new WeakSet();
    function safeClick(el, scrollIntoView) {
      try {
        if (!el) return false;
        if (scrollIntoView && el.scrollIntoView) {
          el.scrollIntoView({ block: "nearest", behavior: "auto" });
        }
        if (el.click) {
          el.click();
          return true;
        }
      } catch (_) {}
      return false;
    }
    function safeClickWithDispatch(el, scrollIntoView) {
      try {
        if (!el) return false;
        if (scrollIntoView && el.scrollIntoView) {
          el.scrollIntoView({ block: "nearest", behavior: "auto" });
        }
        var opts = { bubbles: true, cancelable: true, view: window };
        el.dispatchEvent(new MouseEvent("mousedown", opts));
        el.dispatchEvent(new MouseEvent("mouseup", opts));
        el.dispatchEvent(new MouseEvent("click", opts));
        if (el.click) el.click();
        return true;
      } catch (_) {}
      return false;
    }

    /** EDI Data Portal: empty div.pasta-more.pasta-more-show (label via CSS) and jQuery .morelink. */
    function expandPastaMoreInDocument(root) {
      var n = 0;
      if (!root || !root.querySelectorAll) return 0;
      var toggles = root.querySelectorAll(".pasta-more.pasta-more-show");
      for (var i = 0; i < toggles.length; i++) {
        if (safeClickWithDispatch(toggles[i]) || safeClick(toggles[i])) n++;
      }
      var links = root.querySelectorAll("a.morelink, .morelink");
      for (var j = 0; j < links.length; j++) {
        var el = links[j];
        var txt = (el.textContent || "").replace(/[\s\u00a0]+/g, " ").trim();
        if (!/show\s+more/i.test(txt) || /show\s+less/i.test(txt)) continue;
        if (safeClickWithDispatch(el) || safeClick(el)) n++;
      }
      return n;
    }

    /** When jQuery/PASTA handlers did not run, unhide truncated blocks for PDF capture. */
    function revealPastaMoreFallback(root) {
      if (!root || !root.querySelectorAll) return;
      var spans = root.querySelectorAll(".morecontent span");
      for (var s = 0; s < spans.length; s++) {
        try {
          spans[s].style.display = "inline";
        } catch (_) {}
      }
      var collapsed = root.querySelectorAll(".pasta-more.pasta-more-show");
      for (var c = 0; c < collapsed.length; c++) {
        var btn = collapsed[c];
        try {
          btn.classList.remove("pasta-more-show");
          btn.classList.add("pasta-more-hide");
        } catch (_) {}
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
            } catch (_) {}
            var inner = prev.querySelectorAll(".morecontent span, .pasta-hidden");
            for (var k = 0; k < inner.length; k++) {
              try {
                inner[k].style.display = "";
                inner[k].style.maxHeight = "none";
                inner[k].style.overflow = "visible";
              } catch (_) {}
            }
            prev = prev.previousElementSibling;
          }
          var par = btn.parentElement;
          if (par) {
            if (par.classList) {
              par.classList.remove("pasta-collapsed", "collapsed");
            }
            try {
              par.style.maxHeight = "none";
              par.style.overflow = "visible";
            } catch (_) {}
          }
        } catch (_) {}
      }
    }

    var sel;
    // Socrata "Read more"
    sel = document.querySelectorAll("forge-button.collapse-button");
    for (var i = 0; i < sel.length; i++) {
      if (safeClick(sel[i])) readMore++;
    }
    return wait(150)
      .then(function () {
        return wait(300);
      })
      .then(function () {
        // data.gov / Drupal / Bootstrap toggles: "+ Show Full Description", "Show all data fields".
        // These are often inside Shadow DOM or hydrate after load — shallow querySelector misses them.

        function normalizeLabel(s) {
          return (s || "").replace(/[\s\u00a0]+/g, " ").trim();
        }

        /** Visible label for matching (Drupal/React often put wording in aria-label only). */
        function effectiveToggleLabel(el) {
          if (!el || !el.getAttribute) return normalizeLabel(el && el.textContent);
          var bits = [];
          var al = el.getAttribute("aria-label");
          if (al) bits.push(al);
          var tl = el.getAttribute("title");
          if (tl) bits.push(tl);
          bits.push(el.textContent || "");
          return normalizeLabel(bits.join(" "));
        }

        /** Strip leading + / fullwidth plus / spaces so "+Show all…" matches show… patterns. */
        function labelForTextMatch(el) {
          var s = effectiveToggleLabel(el);
          return normalizeLabel(s)
            .replace(/^[\uFEFF\u200B]+/g, "")
            .replace(/^[\+\uFF0B\u2795\s\u00a0]+/g, "")
            .trim();
        }

        function isToggleLike(el) {
          if (!el || el.nodeType !== 1) return false;
          var tag = el.tagName;
          if (tag === "BUTTON") return true;
          if (tag === "SUMMARY") return true;
          // Anchor toggles often omit href (e.g. DOL <a class="showMore" id="showMore" tabindex="0">).
          if (tag === "A") {
            if (el.classList && el.classList.contains("showMore")) return true;
            if (el.id === "showMore") return true;
            if (el.classList && el.classList.contains("morelink")) return true;
            var ti = el.getAttribute("tabindex");
            if (ti !== null && ti !== "" && ti !== "-1") return true;
            var aRole = (el.getAttribute("role") || "").toLowerCase();
            if (aRole === "button" || aRole === "tab") return true;
            var aDt = (el.getAttribute("data-bs-toggle") || el.getAttribute("data-toggle") || "").toLowerCase();
            if (aDt) return true;
            var href = el.getAttribute("href");
            if (href && href.charAt(0) === "#") return true;
            return false;
          }
          if (tag === "INPUT" && (el.type === "button" || el.type === "submit")) return true;
          var role = (el.getAttribute("role") || "").toLowerCase();
          if (role === "button" || role === "link" || role === "tab") return true;
          var dt = (el.getAttribute("data-bs-toggle") || el.getAttribute("data-toggle") || "").toLowerCase();
          if (dt && dt.indexOf("collapse") !== -1) return true;
          if (el.classList && el.classList.contains("btn")) return true;
          if (el.classList && el.classList.contains("usa-accordion__button")) return true;
          if (el.classList && el.classList.contains("fieldset-title")) return true;
          return false;
        }

        function walkInteractiveDeep(root, out) {
          if (!root || root.nodeType !== 1) return;
          if (isToggleLike(root)) out.push(root);
          var sr = root.shadowRoot;
          if (sr) walkInteractiveDeep(sr, out);
          for (var c = root.firstElementChild; c; c = c.nextElementSibling) {
            walkInteractiveDeep(c, out);
          }
        }

        function collectInteractiveDeep() {
          var out = [];
          walkInteractiveDeep(document.documentElement, out);
          var iframes = document.getElementsByTagName("iframe");
          for (var f = 0; f < iframes.length; f++) {
            try {
              var idoc = iframes[f].contentDocument;
              if (idoc && idoc.documentElement) walkInteractiveDeep(idoc.documentElement, out);
            } catch (e) {}
          }
          return out;
        }

        function expandBootstrapTargetFromTrigger(el) {
          try {
            var root = el.ownerDocument || document;
            var sel = (el.getAttribute && (el.getAttribute("data-bs-target") || el.getAttribute("data-target"))) || "";
            if (!sel) {
              var href = el.getAttribute && el.getAttribute("href");
              if (href && href.charAt(0) === "#") sel = href;
            }
            if (!sel || sel.charAt(0) !== "#") return false;
            var tgt = root.querySelector(sel);
            if (!tgt || !tgt.classList || !tgt.classList.contains("collapse")) return false;
            if (tgt.classList.contains("show")) return true;
            tgt.classList.add("show");
            tgt.style.height = "auto";
            tgt.style.overflow = "visible";
            if (el.setAttribute) el.setAttribute("aria-expanded", "true");
            if (el.classList) el.classList.remove("collapsed");
            return true;
          } catch (_) {
            return false;
          }
        }

        function clickToggleOnce(el) {
          try {
            el.scrollIntoView({ block: "nearest", behavior: "auto" });
          } catch (_) {}
          try {
            var det = el.closest && el.closest("details");
            if (el.tagName === "SUMMARY" && det) {
              det.open = true;
              return true;
            }
          } catch (_) {}
          if (expandBootstrapTargetFromTrigger(el)) return true;
          if (safeClickWithDispatch(el, false)) return true;
          return safeClick(el, false);
        }

        function expandNonAccordionCollapsesInDocument(doc) {
          if (!doc || !doc.querySelectorAll) return 0;
          var n = 0;
          var sel = doc.querySelectorAll(".collapse:not(.show)");
          for (var i = 0; i < sel.length; i++) {
            var panel = sel[i];
            if (panel.classList.contains("accordion-collapse")) continue;
            panel.classList.add("show");
            panel.style.height = "auto";
            panel.style.overflow = "visible";
            var pid = panel.id;
            if (pid) {
              var trig = doc.querySelector(
                "[aria-controls=\"" + pid + "\"], [href=\"#" + pid + "\"], [data-bs-target=\"#" + pid + "\"], [data-target=\"#" + pid + "\"]"
              );
              if (trig) {
                trig.setAttribute("aria-expanded", "true");
                if (trig.classList) trig.classList.remove("collapsed");
              }
            }
            n++;
          }
          return n;
        }

        function expandAllDetailsInDocument(doc) {
          if (!doc || !doc.querySelectorAll) return 0;
          var n = 0;
          var dets = doc.querySelectorAll("details:not([open])");
          for (var i = 0; i < dets.length; i++) {
            try {
              dets[i].open = true;
              n++;
            } catch (_) {}
          }
          return n;
        }

        /**
         * Drupal fieldsets (e.g. DOL data.dol.gov): "Show all data fields" is often a
         * legend link; the fieldset may use .collapsed or only hide .fieldset-wrapper.
         */
        function expandDrupalFieldsetsByLabel(doc, re) {
          if (!doc || !doc.querySelectorAll) return 0;
          var n = 0;
          var seen = {};
          var links = doc.querySelectorAll("fieldset legend a, fieldset legend button");
          for (var i = 0; i < links.length; i++) {
            var link = links[i];
            if (!re.test(labelForTextMatch(link))) continue;
            var fs = link.closest && link.closest("fieldset");
            if (!fs || seen[fs]) continue;
            seen[fs] = 1;
            fs.classList.remove("collapsed");
            fs.classList.remove("js-fieldset-collapsed");
            var wrap = fs.querySelector(".fieldset-wrapper");
            if (wrap) {
              wrap.style.display = "";
              wrap.style.visibility = "visible";
              wrap.style.height = "auto";
              wrap.style.maxHeight = "none";
            }
            link.setAttribute("aria-expanded", "true");
            try {
              link.click();
            } catch (_) {}
            n++;
          }
          return n;
        }

        function clickElementsMatchingText(re) {
          var n = 0;
          var nodes = collectInteractiveDeep();
          var seen = {};
          for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (seen[el]) continue;
            if (clickedOnceForPdf.has(el)) continue;
            var t = labelForTextMatch(el);
            if (!re.test(t)) continue;
            seen[el] = 1;
            if (clickToggleOnce(el)) {
              n++;
              clickedOnceForPdf.add(el);
            }
          }
          return n;
        }

        /** DOL uses jQuery .click() handlers; native click() may not run them. page.js runs in page world. */
        function tryJqueryTriggerShowMore() {
          try {
            var $ = window.jQuery || window.$;
            if (!$ || !$.fn || !$.fn.trigger) return;
            var sm = document.getElementById("showMore");
            if (!sm || !sm.classList || !sm.classList.contains("showMore")) return;
            $(sm).trigger("click");
          } catch (e) {}
        }

        /** If JS handlers never ran, unhide siblings / parent row (Drupal collapse pattern). */
        function revealDolDataFieldsNearShowMore() {
          var sm = document.getElementById("showMore");
          if (!sm) return;
          function reveal(el) {
            if (!el || el.nodeType !== 1) return;
            try {
              el.classList.remove("hidden", "u-hidden", "hide", "d-none", "collapse");
              el.classList.add("show");
              el.removeAttribute("hidden");
            } catch (_) {}
            try {
              if (el.style && String(el.style.display).toLowerCase() === "none") el.style.display = "block";
              el.style.visibility = "visible";
              el.style.maxHeight = "none";
              el.style.height = "auto";
              el.style.overflow = "visible";
            } catch (_) {}
          }
          var p = sm.parentElement;
          if (p) {
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
        }

        function pulseExpandByText(re, maxRounds, delayMs) {
          var total = 0;
          var round = 0;
          function step() {
            var k = clickElementsMatchingText(re);
            total += k;
            round++;
            if (k > 0 && round < maxRounds) return wait(delayMs).then(step);
            return Promise.resolve(total);
          }
          return step();
        }

        // Partial labels (sites vary: "Show full description", typos, etc.)
        var reFullDesc = /show\s+full\s+desc/i;
        // DOL / Drupal: "+Show all data fields", optional + / spaces; columns / dictionary wording
        var reDataFields =
          /\+?\s*show\s+all\s+(data\s+)?fields?|show\s+all\s+(data\s+)?fields?|view\s+all\s+(data\s+)?fields?|all\s+data\s+fields?|show\s+all\s+columns?|expand\s+(all\s+)?(data\s+)?fields?|field\s+list|data\s+dictionary/i;

        return pulseExpandByText(reFullDesc, 8, 500)
          .then(function (n) {
            fullDescription = n;
            return pulseExpandByText(reDataFields, 8, 600);
          })
          .then(function (n) {
            dataFields = n;
            var fsMain = expandDrupalFieldsetsByLabel(document, reDataFields);
            dataFields += fsMain;
            collapsePanels += expandNonAccordionCollapsesInDocument(document);
            collapsePanels += expandAllDetailsInDocument(document);
            var iframes = document.getElementsByTagName("iframe");
            for (var f = 0; f < iframes.length; f++) {
              try {
                var idoc = iframes[f].contentDocument;
                if (idoc) {
                  dataFields += expandDrupalFieldsetsByLabel(idoc, reDataFields);
                  collapsePanels += expandNonAccordionCollapsesInDocument(idoc);
                  collapsePanels += expandAllDetailsInDocument(idoc);
                }
              } catch (e) {}
            }
            tryJqueryTriggerShowMore();
            revealDolDataFieldsNearShowMore();
          });
      })
      .then(function () {
        // CMS "Show more" - may load more content; keep clicking until no new buttons (max 15 rounds)
        var round = 0, maxRounds = 15;
        function findShowMoreButtons() {
          var byContainer = document.querySelectorAll(".ShowMoreContainer .btn.btn-primary, .ShowMoreContainer button");
          var byText = [];
          var allBtns = document.querySelectorAll("button");
          for (var b = 0; b < allBtns.length; b++) {
            var t = (allBtns[b].textContent || "").trim();
            if (/show\s*more\s*\(/i.test(t) || (t.toLowerCase().indexOf("show more") === 0 && t.length < 25)) {
              byText.push(allBtns[b]);
            }
          }
          var seen = {};
          var out = [];
          for (var i = 0; i < byContainer.length; i++) {
            if (!seen[byContainer[i]]) { seen[byContainer[i]] = 1; out.push(byContainer[i]); }
          }
          for (var k = 0; k < byText.length; k++) {
            if (!seen[byText[k]]) { seen[byText[k]] = 1; out.push(byText[k]); }
          }
          return out;
        }
        function doShowMore() {
          sel = findShowMoreButtons();
          for (var j = 0; j < sel.length; j++) {
            if (safeClick(sel[j])) showMore++;
          }
          round++;
          if (sel.length > 0 && round < maxRounds) {
            return wait(500).then(doShowMore);
          }
          return wait(400);
        }
        return doShowMore();
      })
      .then(function () {
        // EDI / PASTA mapbrowse: .pasta-more.pasta-more-show (label is CSS-only on empty div)
        var round = 0;
        var maxRounds = 12;
        function doPastaMore() {
          pastaMore += expandPastaMoreInDocument(document);
          var iframes = document.getElementsByTagName("iframe");
          for (var f = 0; f < iframes.length; f++) {
            try {
              var idoc = iframes[f].contentDocument;
              if (idoc) pastaMore += expandPastaMoreInDocument(idoc);
            } catch (e) {}
          }
          revealPastaMoreFallback(document);
          for (var f2 = 0; f2 < iframes.length; f2++) {
            try {
              var idoc2 = iframes[f2].contentDocument;
              if (idoc2) revealPastaMoreFallback(idoc2);
            } catch (e2) {}
          }
          var remaining = document.querySelectorAll(".pasta-more.pasta-more-show").length;
          round++;
          if (remaining > 0 && round < maxRounds) {
            return wait(450).then(doPastaMore);
          }
          showMore += pastaMore;
          return wait(350);
        }
        return doPastaMore();
      })
      .then(function () {
        // CMS accordions: expand by DOM (clicks often ignored by React/Bootstrap)
        var panels = document.querySelectorAll(".accordion-collapse.collapse:not(.show)");
        for (var p = 0; p < panels.length; p++) {
          var panel = panels[p];
          var id = panel.id;
          panel.classList.add("show");
          panel.style.height = "auto";
          var btn = id ? document.querySelector("[aria-controls=\"" + id + "\"]") : null;
          if (btn) {
            btn.setAttribute("aria-expanded", "true");
            btn.classList.remove("collapsed");
          }
          accordions++;
        }
        return wait(400);
      })
      .then(function () {
        return wait(200);
      })
      .then(function () {
        expandForAgDataCommons();
        return {
          readMore: readMore,
          showMore: showMore,
          accordions: accordions,
          fullDescription: fullDescription,
          dataFields: dataFields,
          collapsePanels: collapsePanels,
          pastaMore: pastaMore,
        };
      });
  }

  function loadScript(src) {
    return new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = base + src;
      s.onload = resolve;
      (document.head || document.documentElement).appendChild(s);
    });
  }

  var pdfLibsPromise = null;
  function loadPdfLibs() {
    if (!pdfLibsPromise) {
      pdfLibsPromise = loadScript("html2canvas.min.js")
        .then(function () {
          return loadScript("jspdf.umd.min.js");
        })
        .then(function () {
          return loadScript("html2pdf.bundle.min.js");
        });
    }
    return pdfLibsPromise;
  }

  function run() {
    document.dispatchEvent(new CustomEvent("drp-page-ready"));
    document.addEventListener("drp-generate-pdf", function (evt) {
      var detail = (evt && evt.detail) || {};
      var collectorBase = detail.collectorBase;
      loadPdfLibs()
        .then(function () {
          var h = window.html2pdf;
          var fn = typeof h === "function" ? h : h && h.default;
          var html2canvas = window.html2canvas;
          var jsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
          if (!fn) {
            throw new Error("PDF library failed to load");
          }
          return expandForPdf().then(function () {
            var totalHeight = Math.max(
              document.body.scrollHeight,
              document.documentElement.scrollHeight,
              document.body.offsetHeight,
              document.documentElement.offsetHeight
            );
            var totalWidth = Math.max(
              document.body.scrollWidth,
              document.documentElement.scrollWidth,
              document.body.offsetWidth,
              document.documentElement.offsetWidth
            );
            if (totalHeight > MAX_HEIGHT_SINGLE && html2canvas && jsPDF) {
              captureChunked(collectorBase, totalHeight, totalWidth, html2canvas, jsPDF);
            } else {
              captureSingle(collectorBase, fn);
            }
          });
        })
        .catch(function (e) {
          document.dispatchEvent(
            new CustomEvent("drp-pdf-error", { detail: String((e && e.message) || e) })
          );
        });
    });
  }

  function findMainScrollElement() {
    var candidates = [];
    function walk(el) {
      if (!el || el.nodeType !== 1) return;
      try {
        var style = window.getComputedStyle(el);
        var overflow = (style.overflow || "") + (style.overflowY || "") + (style.overflowX || "");
        if (/auto|scroll|overlay/.test(overflow) && el.scrollHeight > el.clientHeight && el.scrollHeight > 500) {
          candidates.push({ el: el, h: el.scrollHeight });
        }
      } catch (_) {}
      for (var i = 0; i < el.children.length; i++) walk(el.children[i]);
    }
    walk(document.body);
    if (candidates.length === 0) return null;
    candidates.sort(function (a, b) { return b.h - a.h; });
    return candidates[0].el;
  }

  function captureChunked(collectorBase, totalHeight, totalWidth, html2canvas, jsPDF) {
    var mainScroll = findMainScrollElement();
    var scrollEl, captureEl, viewportW, viewportH, totalH;
    if (mainScroll && mainScroll.scrollHeight > mainScroll.clientHeight + 100) {
      scrollEl = mainScroll;
      captureEl = mainScroll;
      viewportW = mainScroll.clientWidth;
      viewportH = mainScroll.clientHeight;
      totalH = mainScroll.scrollHeight;
    } else {
      scrollEl = document.scrollingElement || document.documentElement || document.body;
      captureEl = document.body;
      viewportW = window.innerWidth || document.documentElement.clientWidth || totalWidth;
      viewportH = window.innerHeight || document.documentElement.clientHeight || 800;
      totalH = totalHeight;
    }
    var h2c = {
      scale: 2,
      useCORS: true,
      imageTimeout: 20000,
      logging: false,
      width: viewportW,
      height: viewportH,
      x: 0,
      y: 0,
    };
    if (collectorBase) {
      h2c.proxy = collectorBase + "/api/proxy";
    }

    var chunks = Math.ceil(totalH / viewportH);
    var pdf = new jsPDF({ unit: "mm", format: "a4", orientation: "portrait" });
    var pageWidth = pdf.internal.pageSize.getWidth();
    var pageHeight = pdf.internal.pageSize.getHeight();
    var margin = 10;
    var contentW = pageWidth - 2 * margin;
    var contentH = pageHeight - 2 * margin;
    var idx = 0;
    var savedScrollY = (mainScroll && scrollEl === mainScroll) ? scrollEl.scrollTop : (window.scrollY || scrollEl.scrollTop);
    var savedScrollX = (mainScroll && scrollEl === mainScroll) ? scrollEl.scrollLeft : (window.scrollX || scrollEl.scrollLeft);

    function wait(ms) {
      return new Promise(function (r) {
        setTimeout(r, ms);
      });
    }

    function waitForPaint() {
      return new Promise(function (r) {
        requestAnimationFrame(function () {
          requestAnimationFrame(r);
        });
      });
    }

    function restoreScroll() {
      if (scrollEl === mainScroll) {
        scrollEl.scrollTop = savedScrollY;
        scrollEl.scrollLeft = savedScrollX;
      } else {
        window.scrollTo(savedScrollX, savedScrollY);
      }
    }
    function next() {
      if (idx >= chunks) {
        restoreScroll();
        var blob = pdf.output("blob");
        var fr = new FileReader();
        fr.onload = function () {
          var b64 = fr.result.split(",")[1];
          document.dispatchEvent(new CustomEvent("drp-pdf-ready", { detail: b64 }));
        };
        fr.readAsDataURL(blob);
        return;
      }
      var scrollY = idx * viewportH;
      if (mainScroll && scrollEl === mainScroll) {
        scrollEl.scrollTop = scrollY;
      } else {
        window.scrollTo(0, scrollY);
      }
      wait(350)
        .then(waitForPaint)
        .then(function () {
          var opts = Object.assign({}, h2c, {
            scrollX: scrollEl.scrollLeft || 0,
            scrollY: scrollEl.scrollTop || scrollY,
            windowWidth: viewportW,
            windowHeight: viewportH,
          });
          return html2canvas(captureEl, opts);
        })
        .then(function (canvas) {
          var imgData = canvas.toDataURL("image/jpeg", 0.98);
          var imgW = canvas.width;
          var imgH = canvas.height;
          if (imgW > 0 && imgH > 0) {
            var ratioW = contentW / imgW;
            var ratioH = contentH / imgH;
            var ratio = Math.min(ratioW, ratioH);
            var w = imgW * ratio;
            var h = imgH * ratio;
            if (idx > 0) pdf.addPage();
            pdf.addImage(imgData, "JPEG", margin, margin, w, h, undefined, "FAST");
          }
          idx++;
          next();
        })
        .catch(function (e) {
          restoreScroll();
          document.dispatchEvent(
            new CustomEvent("drp-pdf-error", { detail: String((e && e.message) || e) })
          );
        });
    }
    next();
  }

  function captureSingle(collectorBase, fn) {
    var h2c = {
      scale: 2,
      useCORS: true,
      imageTimeout: 20000,
      logging: false,
      windowWidth: document.documentElement.scrollWidth,
      windowHeight: document.documentElement.scrollHeight,
    };
    if (collectorBase) {
      h2c.proxy = collectorBase + "/api/proxy";
    }
    var opt = {
      margin: 10,
      filename: "page.pdf",
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: h2c,
      jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
    };
    fn()
      .set(opt)
      .from(document.body)
      .toPdf()
      .get("pdf")
      .then(function (pdf) {
        var blob = pdf.output("blob");
        var fr = new FileReader();
        fr.onload = function () {
          var b64 = fr.result.split(",")[1];
          document.dispatchEvent(new CustomEvent("drp-pdf-ready", { detail: b64 }));
        };
        fr.readAsDataURL(blob);
      })
      .catch(function (e) {
        document.dispatchEvent(
          new CustomEvent("drp-pdf-error", { detail: String((e && e.message) || e) })
        );
      });
  }

  // Expansion can run as soon as this script loads; PDF libs only needed for in-page PDF path.
  function attachExpandOnly() {
    function signalReady() {
      document.dispatchEvent(new CustomEvent("drp-expand-ready"));
    }
    signalReady();
    document.addEventListener("drp-expand-ping", signalReady);
    document.addEventListener("drp-expand-for-pdf", function () {
      expandForPdf()
        .then(function (counts) {
          document.dispatchEvent(new CustomEvent("drp-expand-done", { detail: counts }));
        })
        .catch(function (e) {
          document.dispatchEvent(new CustomEvent("drp-expand-done", { detail: { error: String((e && e.message) || e) } }));
        });
    });
  }
  attachExpandOnly();
  run();
})();
