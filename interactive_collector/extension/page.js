/**
 * Runs in page context (injected via script src). Loads html2pdf and listens for
 * drp-generate-pdf; on receipt, generates PDF, converts to base64, dispatches drp-pdf-ready.
 * Must be a separate file - inline scripts are blocked by CSP.
 */
(function () {
  var base = document.currentScript.src.replace(/\/[^/]*$/, "/");
  var script = document.createElement("script");
  script.src = base + "html2pdf.bundle.min.js";
  script.onload = function () {
    var h = window.html2pdf;
    var fn = typeof h === "function" ? h : h && h.default;
    if (!fn) return;
    document.addEventListener("drp-generate-pdf", function (evt) {
      var detail = (evt && evt.detail) || {};
      var collectorBase = detail.collectorBase;
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
          document.dispatchEvent(new CustomEvent("drp-pdf-error", { detail: String((e && e.message) || e) }));
        });
    });
  };
  (document.head || document.documentElement).appendChild(script);
})();
