/**
 * Runs in page context (injected via script src). Loads html2pdf, html2canvas, jsPDF
 * and listens for drp-generate-pdf; generates PDF (chunked for long pages to avoid
 * canvas size limits), converts to base64, dispatches drp-pdf-ready.
 */
(function () {
  var base = document.currentScript.src.replace(/\/[^/]*$/, "/");
  var CHUNK_HEIGHT = 6000;
  var MAX_HEIGHT_SINGLE = 7000;

  function loadScript(src) {
    return new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = base + src;
      s.onload = resolve;
      (document.head || document.documentElement).appendChild(s);
    });
  }

  function run() {
    var h = window.html2pdf;
    var fn = typeof h === "function" ? h : h && h.default;
    var html2canvas = window.html2canvas;
    var jsPDF = (window.jspdf && window.jspdf.jsPDF) || window.jsPDF;
    if (!fn) return;

    document.addEventListener("drp-generate-pdf", function (evt) {
      var detail = (evt && evt.detail) || {};
      var collectorBase = detail.collectorBase;
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

  loadScript("html2canvas.min.js")
    .then(function () {
      return loadScript("jspdf.umd.min.js");
    })
    .then(function () {
      return loadScript("html2pdf.bundle.min.js");
    })
    .then(run);
})();
