/**
 * Runs in page context (injected via script src). Loads html2pdf, html2canvas, jsPDF
 * and listens for drp-generate-pdf; generates PDF (chunked for long pages to avoid
 * canvas size limits), converts to base64, dispatches drp-pdf-ready.
 * Before capture, expands "read more", "Show more", and accordions (Socrata + CMS).
 */
(function () {
  try {
    console.log("[DRP expand] page.js loaded");
  } catch (e) {}
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
   * - CMS: accordions - expand one at a time, re-query after each (Bootstrap/React)
   * Returns { readMore, showMore, accordions } counts.
   */
  var DRP_DEBUG = true;
  function drpLog() {
    if (DRP_DEBUG && typeof console !== "undefined" && console.log) {
      var a = ["[DRP expand]"];
      for (var i = 0; i < arguments.length; i++) a.push(arguments[i]);
      console.log.apply(console, a);
    }
  }

  function expandForPdf() {
    drpLog("start");
    var readMore = 0, showMore = 0, accordions = 0;
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
    var sel;
    // Socrata "Read more"
    sel = document.querySelectorAll("forge-button.collapse-button");
    for (var i = 0; i < sel.length; i++) {
      if (safeClick(sel[i])) readMore++;
    }
    drpLog("Socrata read more: found", sel.length, "clicked", readMore);
    return wait(300)
      .then(function () {
        // CMS "Show more" - may load more content; keep clicking until no new buttons (max 15 rounds)
        var round = 0, maxRounds = 15;
        function doShowMore() {
          sel = document.querySelectorAll(".ShowMoreContainer .btn.btn-primary, .ShowMoreContainer button");
          for (var j = 0; j < sel.length; j++) {
            if (safeClick(sel[j])) showMore++;
          }
          drpLog("Show more round", round + 1, "found", sel.length, "clicked this round", sel.length, "total showMore", showMore);
          round++;
          if (sel.length > 0 && round < maxRounds) {
            return wait(500).then(doShowMore);
          }
          return wait(400);
        }
        return doShowMore();
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
        if (panels.length > 0) drpLog("accordions: expanded", panels.length, "via DOM");
        return wait(400);
      })
      .then(function () {
        return wait(600);
      })
      .then(function () {
        drpLog("done", { readMore: readMore, showMore: showMore, accordions: accordions });
        return { readMore: readMore, showMore: showMore, accordions: accordions };
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

  function run() {
    try {
      console.log("[DRP expand] in-page PDF ready (html2pdf loaded)");
    } catch (e) {}
    document.dispatchEvent(new CustomEvent("drp-page-ready"));
    var h = window.html2pdf;
    var fn = typeof h === "function" ? h : h && h.default;
    var html2canvas = window.html2canvas;
    var jsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
    if (!fn) return;

    document.addEventListener("drp-generate-pdf", function (evt) {
      var detail = (evt && evt.detail) || {};
      var collectorBase = detail.collectorBase;
      expandForPdf()
        .then(function () {
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
    try {
      console.log("[DRP expand] ready for expansion");
    } catch (e) {}
    document.dispatchEvent(new CustomEvent("drp-expand-ready"));
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

  loadScript("html2canvas.min.js")
    .then(function () {
      return loadScript("jspdf.umd.min.js");
    })
    .then(function () {
      return loadScript("html2pdf.bundle.min.js");
    })
    .then(run);
})();
