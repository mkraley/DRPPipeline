"""
Flask app for Interactive Collector.

Multi-pane layout: scoreboard (left), Source pane, Linked pane.
Links open in the Linked pane so you can see where you came from.

When the pipeline DB is available (config DRP_DB_PATH or default drp_pipeline.db),
the app loads the first eligible project (prereq=sourcing, no errors) on start,
and supports Next (next eligible) and Load by DRPID.

When the original source page is retrieved and we have a DRPID, an output folder
is created (or emptied) and folder_path is stored in _result and in Storage.
Save button converts checked scoreboard pages to PDF in that folder.
"""

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import requests
from flask import Flask, redirect, request, render_template_string, url_for

from utils.file_utils import create_output_folder, sanitize_filename
from utils.url_utils import is_valid_url, fetch_page_body, resolve_catalog_resource_url, BROWSER_HEADERS

app = Flask(__name__)

# Default DB path when not set by orchestrator (standalone run).
DEFAULT_DB_PATH = "drp_pipeline.db"
# Default base output dir when not set by orchestrator (Windows).
DEFAULT_BASE_OUTPUT_DIR = r"C:\Documents\DataRescue\DRPData"

# In-memory scoreboard: list of {url, referrer, status_label}. Referrer None = root.
_scoreboard: List[Dict[str, Any]] = []

# Per-DRPID result: folder_path, downloads list, dataset_size for Save.
_result_by_drpid: Dict[int, Dict[str, Any]] = {}

# Content-Type to file extension for downloads (lowercase type -> extension with dot).
_CONTENT_TYPE_EXT: Dict[str, str] = {
    "application/pdf": ".pdf",
    "text/csv": ".csv",
    "application/csv": ".csv",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "text/plain": ".txt",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def _get_db_path() -> Path:
    """Return db path from Args (when pipeline has initialized it) or default."""
    try:
        from utils.Args import Args
        if getattr(Args, "_initialized", False):
            return Path(Args.db_path)
    except Exception:
        pass
    return Path(DEFAULT_DB_PATH)


def _get_base_output_dir() -> Path:
    """Return base output dir from Args (when pipeline has initialized it) or default."""
    try:
        from utils.Args import Args
        if getattr(Args, "_initialized", False):
            return Path(Args.base_output_dir)
    except Exception:
        pass
    return Path(DEFAULT_BASE_OUTPUT_DIR)


def _ensure_storage(flask_app: Flask) -> None:
    """
    Initialize Storage if not already, using Args.db_path or default.
    Ensures Logger is initialized first (Storage implementations use Logger).
    Idempotent; safe to call on every request that needs Storage.
    """
    from storage import Storage
    try:
        Storage.list_eligible_projects(None, 0)
    except RuntimeError:
        # Logger is used by StorageSQLLite; initialize if not already (e.g. standalone run)
        try:
            from utils.Logger import Logger
            if not getattr(Logger, "_initialized", False):
                Logger.initialize(log_level="WARNING")
        except Exception:
            pass
        path = _get_db_path()
        Storage.initialize("StorageSQLLite", db_path=path)


def _get_first_eligible(flask_app: Flask) -> Optional[Dict[str, Any]]:
    """Return the first eligible project (prereq=sourcing, no errors) or None."""
    _ensure_storage(flask_app)
    from storage import Storage
    projects = Storage.list_eligible_projects("sourcing", 1)
    return projects[0] if projects else None


def _get_next_eligible_after(flask_app: Flask, current_drpid: int) -> Optional[Dict[str, Any]]:
    """Return the next eligible project after current_drpid, or None."""
    _ensure_storage(flask_app)
    from storage import Storage
    # Fetch a chunk and find first with DRPID > current_drpid
    projects = Storage.list_eligible_projects("sourcing", 200)
    for proj in projects:
        if proj["DRPID"] > current_drpid:
            return proj
    return None


def _get_project_by_drpid(flask_app: Flask, drpid: int) -> Optional[Dict[str, Any]]:
    """Return the project record for the given DRPID, or None."""
    _ensure_storage(flask_app)
    from storage import Storage
    return Storage.get(drpid)


def _ensure_output_folder_for_drpid(flask_app: Flask, drpid: int) -> Optional[str]:
    """
    Create or empty the output folder for this DRPID; store in _result (no DB update yet).
    Returns folder_path string or None if creation failed.
    """
    if drpid in _result_by_drpid and _result_by_drpid[drpid].get("folder_path"):
        return _result_by_drpid[drpid]["folder_path"]
    base_path = _get_base_output_dir()
    folder_path = create_output_folder(base_path, drpid)
    if not folder_path:
        return None
    path_str = str(folder_path)
    _result_by_drpid[drpid] = {"folder_path": path_str}
    return path_str


def _folder_path_for_drpid(display_drpid: Optional[str]) -> Optional[str]:
    """Return folder_path from _result_by_drpid for the given display_drpid, or None."""
    if not display_drpid:
        return None
    try:
        drpid = int(display_drpid)
        return _result_by_drpid.get(drpid, {}).get("folder_path")
    except (ValueError, TypeError):
        return None


_INDEX_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Interactive Collector</title>
<style>
  body { margin: 0; font-family: sans-serif; }
  .top { padding: 8px; background: #eee; border-bottom: 1px solid #ccc; }
  .top .drpid { font-weight: bold; margin-right: 4px; }
  .top .top-sep { margin: 0 8px; color: #999; }
  .top input[type="url"] { width: 50%; min-width: 300px; }
  .main { display: flex; height: calc(100vh - 50px); }
  .scoreboard { width: 220px; min-width: 180px; max-width: 50%; resize: horizontal; overflow: auto; padding: 8px; border-right: 1px solid #ccc; background: #fafafa; font-size: 12px; }
  .scoreboard h3 { margin: 0 0 8px 0; }
  .scoreboard ul { list-style: none; padding-left: 12px; margin: 0; }
  .scoreboard li { margin: 4px 0; word-break: break-all; }
  .scoreboard .url { color: #06c; }
  .scoreboard a.url { text-decoration: none; }
  .scoreboard a.url:hover { text-decoration: underline; }
  .scoreboard .status-404 { color: #c00; }
  .scoreboard .status-ok { color: #080; }
  .scoreboard-cb { margin-right: 6px; vertical-align: middle; }
  .btn-save { background: #c00; color: white; border: none; padding: 4px 10px; cursor: pointer; font-size: 12px; border-radius: 3px; margin-left: 8px; }
  .btn-save:hover { background: #a00; }
  #save-progress-modal { display: none; position: fixed; z-index: 9999; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
  #save-progress-modal.show { display: flex; align-items: center; justify-content: center; }
  #save-progress-dialog { background: white; padding: 24px; border-radius: 8px; max-width: 90%; min-width: 320px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
  #save-progress-message { margin: 12px 0; white-space: pre-wrap; word-break: break-all; }
  #save-progress-ok { margin-top: 16px; padding: 8px 20px; cursor: pointer; display: none; }
  .panes { flex: 1; display: flex; flex-direction: row; min-width: 0; }
  .pane { flex: 1; min-width: 120px; min-height: 0; border: 1px solid #ccc; margin: 4px; display: flex; flex-direction: column; overflow: hidden; }
  .pane.source-pane { resize: horizontal; max-width: 80%; }
  .pane-header { padding: 4px 8px; background: #e8e8e8; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pane-header-label { font-weight: bold; }
  .pane-back { margin-right: 6px; font-weight: normal; }
  .pane-header-sep { margin-right: 4px; }
  .pane-header-url { font-weight: normal; }
  .pane-iframe { flex: 1; width: 100%; border: none; min-height: 200px; }
  .pane-empty { flex: 1; padding: 16px; color: #666; font-size: 14px; }
</style>
</head>
<body>
  <div class="top">
    {% if drpid is not none %}
    <span class="drpid">DRPID: {{ drpid }}</span>
    <span class="top-sep">|</span>
    <form method="get" action="/" style="display:inline;" class="top-form">
      <input type="hidden" name="next" value="1" />
      <input type="hidden" name="current_drpid" value="{{ drpid }}" />
      <button type="submit">Next</button>
    </form>
    <span class="top-sep">|</span>
    {% endif %}
    <form method="get" action="/" style="display:inline;" class="top-form">
      <label for="url">URL:</label>
      <input type="url" id="url" name="url" value="{{ initial_url or '' }}" size="60" placeholder="https://example.com" />
      <button type="submit">Go</button>
    </form>
    <span class="top-sep">|</span>
    <form method="get" action="/" style="display:inline;" class="top-form">
      <label for="load_drpid">Load DRPID:</label>
      <input type="number" id="load_drpid" name="load_drpid" value="" placeholder="e.g. 1" min="1" style="width:70px;" />
      <button type="submit">Load</button>
    </form>
  </div>
  <div class="main">
    <div class="scoreboard">
      <h3>Scoreboard{% if folder_path %} <button type="submit" form="scoreboard-save-form" class="btn-save">Save</button>{% endif %}</h3>
      {% if folder_path %}
      <form id="scoreboard-save-form" method="post" action="{{ url_for('save') }}">
        <input type="hidden" name="drpid" value="{{ drpid or '' }}" />
        <input type="hidden" name="folder_path" value="{{ (folder_path or '') | e }}" />
        <input type="hidden" name="scoreboard_urls_json" value="{{ scoreboard_urls_json | e }}" />
        {{ scoreboard_html | safe }}
      </form>
      {% else %}
      {{ scoreboard_html | safe }}
      {% endif %}
    </div>
    <div class="panes">
      <div class="pane source-pane">
        <div class="pane-header" title="{{ (source_display_url or '') | e }}">Source: {{ (source_display_url or '—') | e }}</div>
        {% if source_srcdoc %}
        <iframe name="source" class="pane-iframe" srcdoc="{{ source_srcdoc | safe }}" sandbox="allow-same-origin allow-scripts allow-forms allow-top-navigation-by-user-activation" title="Source page"></iframe>
        {% else %}
        <div class="pane-empty">{{ source_pane_message or "Enter a URL and click Go, or click a link to open it in the Linked pane." }}</div>
        {% endif %}
      </div>
      <div class="pane">
        <div class="pane-header" title="{{ (linked_display_url or '') | e }}"><span class="pane-header-label">Linked:</span>{% if linked_back_url %} <a href="{{ linked_back_url | e }}" class="pane-back" title="Back to previous page">← Back</a><span class="pane-header-sep"> </span>{% endif %}<span class="pane-header-url">{{ (linked_display_url or '—') | e }}</span></div>
        {% if linked_srcdoc %}
        <iframe name="linked" class="pane-iframe" srcdoc="{{ linked_srcdoc | safe }}" sandbox="allow-same-origin allow-scripts allow-forms allow-top-navigation-by-user-activation" title="Linked page"></iframe>
        {% else %}
        <div class="pane-empty">
          {{ linked_pane_message or "Click a link in Source (or Linked) to open it here." }}
        </div>
        {% endif %}
      </div>
    </div>
  </div>
  <div id="save-progress-modal">
    <div id="save-progress-dialog">
      <strong>Saving PDFs</strong>
      <div id="save-progress-message">Starting...</div>
      <button type="button" id="save-progress-ok">Close</button>
    </div>
  </div>
  {% if show_auto_download %}
  <span id="auto-download-data" data-url="{{ linked_binary_url | e }}" data-drpid="{{ (drpid or '') | e }}" data-referrer="{{ (linked_binary_referrer or '') | e }}" style="display:none"></span>
  <script>
  (function(){
    var el = document.getElementById("auto-download-data");
    if (!el) return;
    var url = el.getAttribute("data-url") || "";
    var drpid = (el.getAttribute("data-drpid") || "").trim();
    var referrer = el.getAttribute("data-referrer") || "";
    if (!url || !drpid) return;
    var modal = document.getElementById("save-progress-modal");
    var msg = document.getElementById("save-progress-message");
    var closeBtn = document.getElementById("save-progress-ok");
    if (!modal || !msg) return;
    var titleEl = modal.querySelector("strong");
    if (titleEl) titleEl.textContent = "Downloading file";
    modal.classList.add("show");
    if (closeBtn) closeBtn.style.display = "none";
    msg.textContent = "Downloading...";
    var reloadOnClose = false;
    if (closeBtn) closeBtn.onclick = function() {
      modal.classList.remove("show");
      if (reloadOnClose) {
        var u = new URL(window.location.href);
        u.searchParams.set("downloaded", "1");
        window.location.href = u.toString();
      }
    };
    var fd = new FormData();
    fd.append("url", url);
    fd.append("drpid", drpid);
    fd.append("referrer", referrer);
    fetch("{{ url_for('download_file') }}", { method: "POST", body: fd })
      .then(function(res) {
        if (!res.ok) {
          return res.text().then(function(t) {
            msg.textContent = "Error " + res.status + ": " + (t || res.statusText || "request failed");
            if (closeBtn) closeBtn.style.display = "inline-block";
          });
        }
        if (!res.body) throw new Error("No body");
        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buf = "";
        function read() {
          return reader.read().then(function(r) {
            if (r.done) return;
            buf += decoder.decode(r.value, { stream: true });
            var lines = buf.split("\\n");
            buf = lines.pop();
            for (var i = 0; i < lines.length; i++) {
              var line = lines[i];
              if (line.startsWith("SAVING\\t")) msg.textContent = "Downloading " + (line.split("\\t")[1] || "");
              else if (line.startsWith("PROGRESS\\t")) {
                var p = line.split("\\t");
                var w = parseInt(p[1], 10);
                var t = p[2];
                msg.textContent = t ? "Downloaded " + (w < 1024 ? w + " B" : (w < 1024*1024 ? (w/1024).toFixed(1) + " KB" : (w/(1024*1024)).toFixed(1) + " MB")) + " / " + (parseInt(t,10) < 1024*1024 ? (parseInt(t,10)/1024).toFixed(1) + " KB" : (parseInt(t,10)/(1024*1024)).toFixed(1) + " MB") : "Downloaded " + (w < 1024 ? w + " B" : (w/(1024*1024)).toFixed(1) + " MB");
              } else if (line.startsWith("DONE\\t")) {
                var doneParts = line.split("\\t");
                var savedName = doneParts[1] ? doneParts[1].trim() : "";
                var extDisplay = (doneParts[3] && doneParts[3].trim()) ? " " + doneParts[3].trim() : "";
                msg.textContent = savedName ? "Download complete. Saved as " + savedName : "Download complete.";
                if (closeBtn) closeBtn.style.display = "inline-block";
                var parentLi = null;
                var urls = document.querySelectorAll(".scoreboard .url");
                for (var i = 0; i < urls.length; i++) {
                  if (urls[i].getAttribute("title") === referrer) {
                    parentLi = urls[i].closest("li");
                    break;
                  }
                }
                var ul = parentLi ? (parentLi.querySelector("ul") || (function() { var u = document.createElement("ul"); parentLi.appendChild(u); return u; })()) : document.querySelector(".scoreboard ul");
                if (ul) {
                  var li = document.createElement("li");
                  var spanUrl = document.createElement("span");
                  spanUrl.className = "url";
                  spanUrl.title = savedName;
                  spanUrl.textContent = savedName || "file";
                  var spanStatus = document.createElement("span");
                  spanStatus.className = "status-ok";
                  spanStatus.textContent = "(DL" + extDisplay + ")";
                  li.appendChild(spanUrl);
                  li.appendChild(document.createTextNode(" "));
                  li.appendChild(spanStatus);
                  ul.appendChild(li);
                } else {
                  reloadOnClose = true;
                }
                return;
              } else if (line.startsWith("ERROR\\t")) {
                msg.textContent = "Error: " + (line.split("\\t")[1] || "unknown");
                if (closeBtn) closeBtn.style.display = "inline-block";
                return;
              }
            }
            return read();
          });
        }
        return read();
      })
      .catch(function(e) {
        msg.textContent = "Error: " + (e.message || "request failed");
        if (closeBtn) closeBtn.style.display = "inline-block";
      });
  })();
  </script>
  {% endif %}
  <script>
  (function() {
    var form = document.getElementById("scoreboard-save-form");
    var modal = document.getElementById("save-progress-modal");
    var messageEl = document.getElementById("save-progress-message");
    var okBtn = document.getElementById("save-progress-ok");
    var reloadOnClose = false;

    function showModal(title) {
      if (!modal) { alert(title || "Progress"); return; }
      var strong = modal.querySelector("strong");
      if (strong) strong.textContent = title || "Progress";
      modal.classList.add("show");
      if (okBtn) okBtn.style.display = "none";
    }
    function hideModal() {
      if (modal) modal.classList.remove("show");
      if (reloadOnClose) {
        reloadOnClose = false;
        window.location.reload();
      }
    }

    if (form) {
      form.addEventListener("submit", function(ev) {
        ev.preventDefault();
        showModal("Saving PDFs");
        messageEl.textContent = "Starting...";
        var formData = new FormData(form);
        fetch("{{ url_for('save') }}", { method: "POST", body: formData })
          .then(function(res) {
            if (!res.body) throw new Error("No body");
            var reader = res.body.getReader();
            var decoder = new TextDecoder();
            var buf = "";
            function read() {
              return reader.read().then(function(r) {
                if (r.done) return;
                buf += decoder.decode(r.value, { stream: true });
                var lines = buf.split("\\n");
                buf = lines.pop();
                for (var i = 0; i < lines.length; i++) {
                  var line = lines[i];
                  if (line.startsWith("SAVING\\t")) {
                    var parts = line.split("\\t");
                    if (parts.length >= 4) messageEl.textContent = "Saving " + parts[1] + " " + parts[2] + "/" + parts[3];
                  } else if (line.startsWith("SUMMARY\\t")) {
                    try {
                      var summary = JSON.parse(line.slice(8));
                      var s = "Downloaded files:\\n";
                      for (var j = 0; j < summary.length; j++) {
                        var f = summary[j];
                        var sz = (f.size !== undefined) ? (f.size < 1024 ? f.size + " B" : (f.size < 1024*1024 ? (f.size/1024).toFixed(1) + " KB" : (f.size/(1024*1024)).toFixed(1) + " MB") : "";
                        s += (f.filename || f.path || "?") + " — " + sz + "\\n";
                      }
                      messageEl.textContent = s;
                    } catch (_) {}
                  } else if (line.startsWith("TOTAL_SIZE\\t")) {
                    var total = parseInt(line.split("\\t")[1], 10) || 0;
                    var totalStr = total < 1024 ? total + " B" : (total < 1024*1024 ? (total/1024).toFixed(1) + " KB" : (total/(1024*1024)).toFixed(1) + " MB");
                    messageEl.textContent = (messageEl.textContent || "") + "\\nTotal size: " + totalStr;
                  } else if (line.startsWith("DONE\\t")) {
                    var n = line.split("\\t")[1] || "0";
                    messageEl.textContent = (messageEl.textContent ? messageEl.textContent + "\\n\\n" : "") + "Saved " + n + " file(s).";
                    okBtn.style.display = "inline-block";
                    return;
                  } else if (line.startsWith("ERROR\\t")) {
                    messageEl.textContent = "Error: " + (line.split("\\t")[1] || "unknown");
                    okBtn.style.display = "inline-block";
                    return;
                  }
                }
                return read();
              });
            }
            return read();
          })
          .catch(function(e) {
            messageEl.textContent = "Error: " + (e.message || "request failed");
            okBtn.style.display = "inline-block";
          });
      });
    }

    function runDownloadBinary(btn) {
      window.__downloadBinaryClicked = true;
      try {
        showModal("Downloading file");
      } catch (e) {
        alert("Download: " + (e.message || e));
        return;
      }
      if (!modal || !messageEl) {
        alert("Downloading file (modal not found)");
        return;
      }
      if (!btn) return;
      var url = btn.getAttribute("data-url");
      var referrer = btn.getAttribute("data-referrer") || "";
      var drpid = (btn.getAttribute("data-drpid") || "").trim();
      if (!drpid) {
        var el = document.querySelector('input[name="drpid"]');
        drpid = el ? (el.value || "").trim() : "";
      }
      if (!url || !drpid) {
        messageEl.textContent = "No project (DRPID) set. Load a project (Load DRPID) first.";
        if (okBtn) okBtn.style.display = "inline-block";
        return;
      }
      messageEl.textContent = "Downloading...";
      var fd = new FormData();
      fd.append("url", url);
      fd.append("drpid", drpid);
      fd.append("referrer", referrer);
      var downloadUrl = "{{ url_for('download_file') }}";
      fetch(downloadUrl, { method: "POST", body: fd })
        .then(function(res) {
          if (!res.ok) {
            return res.text().then(function(t) {
              messageEl.textContent = "Error " + res.status + ": " + (t || res.statusText || "request failed");
              okBtn.style.display = "inline-block";
            });
          }
          if (!res.body) throw new Error("No body");
          var reader = res.body.getReader();
          var decoder = new TextDecoder();
          var buf = "";
          function read() {
            return reader.read().then(function(r) {
              if (r.done) return;
              buf += decoder.decode(r.value, { stream: true });
              var lines = buf.split("\\n");
              buf = lines.pop();
              for (var i = 0; i < lines.length; i++) {
                var line = lines[i];
                if (line.startsWith("SAVING\\t")) messageEl.textContent = "Downloading " + line.split("\\t")[1];
                else if (line.startsWith("PROGRESS\\t")) {
                  var p = line.split("\\t");
                  var w = parseInt(p[1], 10);
                  var t = p[2];
                  messageEl.textContent = t ? "Downloaded " + (w < 1024 ? w + " B" : (w < 1024*1024 ? (w/1024).toFixed(1) + " KB" : (w/(1024*1024)).toFixed(1) + " MB")) + " / " + (parseInt(t,10) < 1024*1024 ? (parseInt(t,10)/1024).toFixed(1) + " KB" : (parseInt(t,10)/(1024*1024)).toFixed(1) + " MB") : "Downloaded " + (w < 1024 ? w + " B" : (w/(1024*1024)).toFixed(1) + " MB");
                } else if (line.startsWith("DONE\\t")) {
                  messageEl.textContent = "Download complete.";
                  okBtn.style.display = "inline-block";
                  reloadOnClose = true;
                  return;
                } else if (line.startsWith("ERROR\\t")) {
                  messageEl.textContent = "Error: " + (line.split("\\t")[1] || "unknown");
                  okBtn.style.display = "inline-block";
                  return;
                }
              }
              return read();
            });
          }
          return read();
        })
        .catch(function(e) {
          messageEl.textContent = "Error: " + (e.message || "request failed");
          okBtn.style.display = "inline-block";
        });
    }
    window.__downloadBinary = runDownloadBinary;

    var downloadBtn = document.getElementById("btn-download-binary");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", function(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        runDownloadBinary(ev.currentTarget);
      });
    }
    document.addEventListener("click", function(ev) {
      var btn = ev.target && ev.target.closest && ev.target.closest(".btn-download-binary");
      if (btn) { ev.preventDefault(); ev.stopPropagation(); runDownloadBinary(btn); }
    }, true);

    if (okBtn) okBtn.addEventListener("click", function() { hideModal(); });
  })();
  </script>
</body>
</html>
"""


def _base_url_for_page(page_url: str) -> str:
    """Return the base URL (directory) for resolving relative URLs on the page."""
    if page_url.endswith("/"):
        return page_url
    return urljoin(page_url + "/", "..")


def _inject_base_into_html(html_body: str, page_url: str) -> str:
    """Inject <base href="..."> into the first <head> so relative CSS/JS/images load."""
    base_href = _base_url_for_page(page_url)
    base_escaped = base_href.replace("&", "&amp;").replace('"', "&quot;")
    base_tag = f'<base href="{base_escaped}">'
    return re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html_body, count=1, flags=re.IGNORECASE)


def _rewrite_links_to_app(
    html_body: str,
    page_url: str,
    app_root_url: str,
    source_url: str,
    current_page_url: str,
    drpid: Optional[str] = None,
) -> str:
    """
    Rewrite <a href="..."> so clicks load in the Linked pane. Builds
    ?source_url=...&linked_url=...&referrer=... so the new page opens in Linked
    and both panes are re-rendered. If drpid is set, appends it to preserve current project.
    Only rewrites http/https links.
    """
    def repl(match: re.Match) -> str:
        before_href = match.group(1)
        quote_char = match.group(2)
        href_value = match.group(3).strip()
        after_href = match.group(4)
        if not href_value or href_value.startswith("#") or href_value.startswith("javascript:"):
            return match.group(0)
        if href_value.startswith("mailto:") or href_value.startswith("tel:"):
            return match.group(0)
        absolute_url = urljoin(page_url, href_value)
        if not absolute_url.startswith("http://") and not absolute_url.startswith("https://"):
            return match.group(0)
        # Resolve catalog links when clicked (in the route), not here, to avoid slow page loads.
        params = (
            "source_url=" + quote(source_url, safe="")
            + "&linked_url=" + quote(absolute_url, safe="")
            + "&referrer=" + quote(current_page_url, safe="")
        )
        if drpid:
            params += "&drpid=" + quote(drpid, safe="")
        app_url = app_root_url.rstrip("/") + "/?" + params
        escaped = app_url.replace("&", "&amp;").replace('"', "&quot;")
        return f'<a {before_href} target="_top" href={quote_char}{escaped}{quote_char} {after_href}>'

    return re.sub(
        r"<a\s+([^>]*?)href\s*=\s*([\"'])([^\"']*)\2([^>]*)>",
        repl,
        html_body,
        flags=re.IGNORECASE,
    )


def _is_displayable_text(content_type: Optional[str]) -> bool:
    """Return True if we should show the response body as text (not binary)."""
    if not content_type:
        return True
    ct = content_type.lower().strip()
    if ct.startswith("text/"):
        return True
    if ct in (
        "application/xml",
        "application/json",
        "application/javascript",
        "application/xhtml+xml",
    ):
        return True
    return False


def _extension_from_content_type(content_type: Optional[str]) -> str:
    """Return extension with leading dot from Content-Type, or empty string."""
    if not content_type or ";" in content_type:
        content_type = (content_type or "").split(";")[0].strip().lower()
    return _CONTENT_TYPE_EXT.get(content_type, "")


def _filename_from_content_disposition(header_value: Optional[str]) -> Optional[str]:
    """Extract filename from Content-Disposition header (filename= or filename*=)."""
    if not header_value:
        return None
    # filename*=UTF-8''encoded
    if "filename*=" in header_value:
        try:
            part = header_value.split("filename*=")[-1].strip().strip(";")
            if part.lower().startswith("utf-8''"):
                from urllib.parse import unquote
                return unquote(part[7:])
            return part.strip("\"'")
        except Exception:
            pass
    # filename="name"
    if "filename=" in header_value:
        try:
            part = header_value.split("filename=", 1)[-1].strip().strip(";").strip("\"'")
            if part:
                return part
        except Exception:
            pass
    return None


def _filename_from_url(url: str) -> str:
    """Last path segment or 'download'."""
    from urllib.parse import urlparse, unquote
    path = urlparse(url).path or ""
    name = (path.rstrip("/").split("/")[-1] or "download")
    return unquote(name)


def _unique_download_basename(base: str, ext: str, used: Dict[str, int]) -> str:
    """Return unique sanitized basename: base.ext or base_1.ext, etc."""
    if not base or base == "download":
        base = "download"
    base = sanitize_filename(base, max_length=80)
    if ext and not base.lower().endswith(ext.lower()):
        base = base + ext
    key = base.lower()
    n = used.get(key, 0)
    used[key] = n + 1
    if n == 0:
        return base
    # insert _n before the extension
    if "." in base:
        stem, suffix = base.rsplit(".", 1)
        return f"{stem}_{n}.{suffix}"
    return f"{base}_{n}"


def _status_label(status_code: int, is_logical_404: bool) -> str:
    """Return human-readable status for display."""
    if status_code == 404:
        return "404 (logical)" if is_logical_404 else "404"
    if status_code == 200:
        return "OK"
    if status_code < 0:
        return f"Error ({status_code})"
    return str(status_code)


def _scoreboard_add(url: str, referrer: Optional[str], status_label: str) -> None:
    """Append a node to the in-memory scoreboard. Marks as dupe if this URL is already present at any level."""
    existing_urls = {n["url"] for n in _scoreboard}
    is_dupe = url in existing_urls
    _scoreboard.append({"url": url, "referrer": referrer, "status_label": status_label, "is_dupe": is_dupe})


def _scoreboard_add_download(
    url: str,
    referrer: Optional[str],
    file_path: str,
    file_size: int,
    extension: str,
    filename: Optional[str] = None,
) -> None:
    """Append a downloaded-file entry to the scoreboard (no checkbox, DL flag + extension)."""
    _scoreboard.append({
        "url": url,
        "referrer": referrer,
        "status_label": "DL",
        "is_dupe": False,
        "is_download": True,
        "file_path": file_path,
        "file_size": file_size,
        "extension": extension or "",
        "filename": filename or "",
    })


def _scoreboard_tree() -> List[Dict[str, Any]]:
    """Return scoreboard as a tree. One node per entry (no merging by URL) so original stays OK, dupes shown separately."""
    nodes = [
        {
            "url": n["url"],
            "referrer": n["referrer"],
            "status_label": n["status_label"],
            "is_dupe": n.get("is_dupe", False),
            "idx": i,
            "children": [],
            "is_download": n.get("is_download", False),
            "file_path": n.get("file_path"),
            "file_size": n.get("file_size", 0),
            "extension": n.get("extension", ""),
            "filename": n.get("filename", ""),
        }
        for i, n in enumerate(_scoreboard)
    ]
    url_to_first_idx: Dict[str, int] = {}
    for i, n in enumerate(nodes):
        if n["url"] not in url_to_first_idx:
            url_to_first_idx[n["url"]] = i
    for n in nodes:
        ref = n["referrer"]
        if ref and ref in url_to_first_idx:
            nodes[url_to_first_idx[ref]]["children"].append(n)
    roots = [n for n in nodes if n["referrer"] is None or n["referrer"] not in url_to_first_idx]
    return roots


def _scoreboard_render_html(
    app_root: str,
    current_source_url: str,
    drpid: Optional[str] = None,
    for_save_form: bool = False,
    linked_url_not_checked: Optional[str] = None,
) -> str:
    """Render scoreboard tree as HTML (nested ul). Checkbox checked for original source and OK non-dupes (except linked_url_not_checked)."""
    roots = _scoreboard_tree()
    if not roots:
        return "<p><em>No pages yet.</em></p>"

    original_source_url = next((n["url"] for n in _scoreboard if n.get("referrer") is None), _scoreboard[0]["url"] if _scoreboard else "")

    def render_node(node: Dict[str, Any]) -> str:
        url = node["url"]
        url_short = url[:80] + ("..." if len(url) > 80 else "")
        status = node["status_label"]
        is_dupe = node.get("is_dupe", False)
        is_download = node.get("is_download", False)
        ext = (node.get("extension") or "").strip()
        if is_download and ext and not ext.startswith("."):
            ext = "." + ext
        status_display = (status + " " + ext).strip() if is_download else (status + " (dupe)" if is_dupe else status)
        status_class = "status-404" if "404" in status and not is_download else "status-ok"
        referrer = node.get("referrer") or current_source_url
        is_ok = "OK" in status
        base_checked = (url == original_source_url and is_ok) or (is_ok and not is_dupe)
        checked = base_checked and (not linked_url_not_checked or url != linked_url_not_checked)
        idx = node.get("idx", 0)
        if is_download:
            cb = ""  # No checkbox for downloads
        elif for_save_form:
            cb = f'<input type="checkbox" class="scoreboard-cb" name="save_url" value="{idx}" {"checked" if checked else ""} />'
        else:
            cb = f'<input type="checkbox" class="scoreboard-cb" {"checked" if checked else ""} />'
        if is_download:
            display_text = (node.get("filename") or "").strip() or url_short
            link = f'<span class="url" title="{html.escape(url)}">{html.escape(display_text)}</span>'
        elif current_source_url:
            params = f"source_url={quote(current_source_url)}&linked_url={quote(url)}&referrer={quote(referrer)}&from_scoreboard=1"
            if drpid:
                params += f"&drpid={quote(drpid, safe='')}"
            link = f'<a class="url" href="{html.escape(app_root)}/?{params}" title="{html.escape(url)}">{html.escape(url_short)}</a>'
        else:
            link = f'<span class="url" title="{html.escape(url)}">{html.escape(url_short)}</span>'
        line = f'<li>{cb} {link} <span class="{status_class}">({html.escape(status_display)})</span></li>'
        if node.get("children"):
            children_html = "".join(render_node(c) for c in node["children"])
            line += f"<ul>{children_html}</ul>"
        return line

    items = "".join(render_node(r) for r in roots)
    return f"<ul>{items}</ul>"


def _prepare_pane_content(
    url_param: str,
    app_root: str,
    source_url: str,
    drpid: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], str]:
    """
    Fetch url_param, inject base, rewrite links. Returns (safe_srcdoc, body_message, status_label).
    """
    status_code, body, content_type, is_logical_404 = fetch_page_body(url_param)
    status_label = _status_label(status_code, is_logical_404)

    if not _is_displayable_text(content_type) and content_type:
        return None, f"Binary content ({html.escape(content_type)}). Not displayed.", status_label
    if (body or "").strip() == "" and _is_displayable_text(content_type):
        return None, "Content could not be displayed (possibly binary or wrong encoding).", status_label

    body_with_base = _inject_base_into_html(body or "", url_param)
    body_rewritten = _rewrite_links_to_app(
        body_with_base, url_param, app_root, source_url, url_param, drpid=drpid
    )
    safe_srcdoc = body_rewritten.replace("&", "&amp;").replace('"', "&quot;")
    return safe_srcdoc, None, status_label


@app.route("/")
def index() -> str:
    """
    Three-pane layout: scoreboard, Source, Linked.

    Initial: ?url=... -> fetch url, show in Source; add root to scoreboard.
    Link click: ?source_url=...&linked_url=...&referrer=... -> fetch both.
    First load (no params): get first eligible project from Storage and show it.
    ?next=1&current_drpid=X -> redirect to next eligible after X.
    ?load_drpid=X -> redirect to project X's URL with drpid=X.
    """
    app_root = request.url_root.rstrip("/") or request.host_url.rstrip("/")
    url_param = request.args.get("url", "").strip()
    source_url_param = request.args.get("source_url", "").strip()
    linked_url_param = request.args.get("linked_url", "").strip()
    referrer_param = request.args.get("referrer", "").strip()
    from_scoreboard = request.args.get("from_scoreboard", "").strip()
    drpid_param = request.args.get("drpid", "").strip()
    display_drpid: Optional[str] = drpid_param if drpid_param else None

    # Next: get next eligible project after current_drpid and redirect
    next_param = request.args.get("next", "").strip()
    current_drpid_param = request.args.get("current_drpid", "").strip()
    if next_param and current_drpid_param:
        try:
            current_drpid = int(current_drpid_param)
            proj = _get_next_eligible_after(app, current_drpid)
            if proj:
                return redirect(
                    url_for("index", url=proj.get("source_url") or "", drpid=proj["DRPID"])
                )
            # No next: stay on same project (or could show message)
        except ValueError:
            pass

    # Load by DRPID: fetch project and redirect to its URL
    load_drpid_param = request.args.get("load_drpid", "").strip()
    if load_drpid_param and not url_param and not source_url_param and not linked_url_param:
        try:
            load_drpid = int(load_drpid_param)
            proj = _get_project_by_drpid(app, load_drpid)
            if proj and proj.get("source_url"):
                return redirect(
                    url_for("index", url=proj["source_url"], drpid=load_drpid)
                )
            # Not found or no URL: fall through to show form (with message later if desired)
        except ValueError:
            pass

    # First load (no URL params): get first eligible from Storage and populate
    if not url_param and not source_url_param and not linked_url_param:
        try:
            proj = _get_first_eligible(app)
            if proj:
                url_param = (proj.get("source_url") or "").strip()
                if url_param:
                    display_drpid = str(proj["DRPID"])
        except RuntimeError:
            pass

    # Initial load: single url=
    if url_param and not source_url_param and not linked_url_param:
        _scoreboard.clear()
        if not is_valid_url(url_param):
            folder_path = _folder_path_for_drpid(display_drpid)
            return render_template_string(
                _INDEX_HTML,
                initial_url=html.escape(url_param),
                scoreboard_html=_scoreboard_render_html(app_root, "", drpid=display_drpid, for_save_form=bool(folder_path)),
                source_srcdoc=None,
                linked_srcdoc=None,
                source_pane_message="Invalid URL. Provide a valid http:// or https:// URL.",
                source_display_url=None,
                linked_display_url=None,
                drpid=display_drpid,
                folder_path=folder_path,
                scoreboard_urls_json=json.dumps([n["url"] for n in _scoreboard]),
                show_auto_download=False,
            )
        safe_srcdoc, body_message, status_label = _prepare_pane_content(
            url_param, app_root, url_param, drpid=display_drpid
        )
        _scoreboard_add(url_param, None, status_label)
        source_srcdoc = safe_srcdoc if body_message is None else None
        if body_message and safe_srcdoc is None:
            source_srcdoc = None
        # When source page was retrieved and we have a DRPID, create/empty output folder and set folder_path
        folder_path: Optional[str] = None
        if display_drpid and body_message is None:
            try:
                folder_path = _ensure_output_folder_for_drpid(app, int(display_drpid))
            except (ValueError, TypeError):
                pass
        if folder_path is None:
            folder_path = _folder_path_for_drpid(display_drpid)
        scoreboard_urls_json = json.dumps([n["url"] for n in _scoreboard])
        return render_template_string(
            _INDEX_HTML,
            initial_url=html.escape(url_param),
            scoreboard_html=_scoreboard_render_html(app_root, url_param, drpid=display_drpid, for_save_form=bool(folder_path)),
            source_srcdoc=source_srcdoc,
            linked_srcdoc=None,
            source_pane_message=body_message,
            source_display_url=url_param,
            linked_display_url=None,
            linked_back_url=None,
            drpid=display_drpid,
            folder_path=folder_path,
            scoreboard_urls_json=scoreboard_urls_json,
            show_auto_download=False,
        )

    # Link click: source_url + linked_url + referrer
    if source_url_param and linked_url_param and referrer_param:
        if not is_valid_url(source_url_param) or not is_valid_url(linked_url_param):
            folder_path = _folder_path_for_drpid(display_drpid)
            return render_template_string(
                _INDEX_HTML,
                initial_url=html.escape(source_url_param),
                scoreboard_html=_scoreboard_render_html(app_root, source_url_param, drpid=display_drpid, for_save_form=bool(folder_path)),
                source_srcdoc=None,
                linked_srcdoc=None,
                source_pane_message=None,
                source_display_url=None,
                linked_display_url=None,
                drpid=display_drpid,
                folder_path=folder_path,
                scoreboard_urls_json=json.dumps([n["url"] for n in _scoreboard]),
                show_auto_download=False,
            )
        # Fetch both panes. For catalog.data.gov links, resolve on click and show the resolved URL in the Linked pane (skip the relay).
        src_srcdoc, src_pane_message, src_status = _prepare_pane_content(
            source_url_param, app_root, source_url_param, drpid=display_drpid
        )
        linked_url_for_fetch = linked_url_param
        linked_display_url = linked_url_param
        resolved_linked: Optional[str] = None
        if linked_url_param.startswith("https://catalog.data.gov"):
            resolved_linked = resolve_catalog_resource_url(linked_url_param)
            if resolved_linked:
                linked_url_for_fetch = resolved_linked
                linked_display_url = resolved_linked
        linked_srcdoc, linked_pane_message, linked_status = _prepare_pane_content(
            linked_url_for_fetch, app_root, source_url_param, drpid=display_drpid
        )
        if not any(n["url"] == source_url_param for n in _scoreboard):
            _scoreboard_add(source_url_param, None, src_status)
        linked_is_binary = (
            linked_srcdoc is None
            and linked_pane_message
            and "Binary content" in (linked_pane_message or "")
        )
        if not from_scoreboard and not linked_is_binary:
            _scoreboard_add(linked_url_for_fetch, referrer_param, linked_status)
        # else: from_scoreboard click, or binary (DL entry added when download completes)
        folder_path = _folder_path_for_drpid(display_drpid)
        if folder_path is None and display_drpid:
            try:
                folder_path = _ensure_output_folder_for_drpid(app, int(display_drpid))
            except (ValueError, TypeError):
                pass
        linked_srcdoc_for_display = linked_srcdoc
        linked_display_url_when_binary: Optional[str] = None
        if linked_is_binary and referrer_param:
            if referrer_param == source_url_param:
                linked_srcdoc_for_display = src_srcdoc
                linked_display_url_when_binary = source_url_param
            elif is_valid_url(referrer_param):
                ref_srcdoc, _ref_msg, _ref_status = _prepare_pane_content(
                    referrer_param, app_root, source_url_param, drpid=display_drpid
                )
                if ref_srcdoc:
                    linked_srcdoc_for_display = ref_srcdoc
                    linked_display_url_when_binary = referrer_param
                else:
                    linked_srcdoc_for_display = src_srcdoc
                    linked_display_url_when_binary = source_url_param
            else:
                linked_srcdoc_for_display = src_srcdoc
                linked_display_url_when_binary = source_url_param
        elif linked_is_binary:
            linked_srcdoc_for_display = src_srcdoc
            linked_display_url_when_binary = source_url_param
        if linked_display_url_when_binary is not None:
            linked_display_url = linked_display_url_when_binary
        show_auto_download = (
            linked_is_binary
            and bool(folder_path)
            and bool(linked_url_for_fetch)
            and not request.args.get("downloaded")
        )
        linked_back_url = None
        if linked_srcdoc_for_display and referrer_param and referrer_param != source_url_param:
            _kwargs = {"source_url": source_url_param, "linked_url": referrer_param, "referrer": source_url_param, "from_scoreboard": "1"}
            if display_drpid:
                _kwargs["drpid"] = display_drpid
            linked_back_url = url_for("index", **_kwargs)
        return render_template_string(
            _INDEX_HTML,
            initial_url=html.escape(source_url_param),
            scoreboard_html=_scoreboard_render_html(
                app_root, source_url_param, drpid=display_drpid, for_save_form=bool(folder_path),
                linked_url_not_checked=linked_url_for_fetch if linked_is_binary else None,
            ),
            source_srcdoc=src_srcdoc,
            linked_srcdoc=linked_srcdoc_for_display,
            source_pane_message=src_pane_message,
            linked_pane_message=linked_pane_message,
            source_display_url=source_url_param,
            linked_display_url=linked_display_url,
            linked_back_url=linked_back_url,
            drpid=display_drpid,
            folder_path=folder_path,
            scoreboard_urls_json=json.dumps([n["url"] for n in _scoreboard]),
            linked_is_binary=linked_is_binary,
            linked_binary_url=linked_url_for_fetch if linked_is_binary else None,
            linked_binary_referrer=referrer_param if linked_is_binary else None,
            show_auto_download=show_auto_download,
        )

    # No URL: show form and empty panes
    folder_path = _folder_path_for_drpid(display_drpid)
    return render_template_string(
        _INDEX_HTML,
        initial_url="",
        scoreboard_html=_scoreboard_render_html(app_root, "", drpid=display_drpid, for_save_form=bool(folder_path)),
        source_srcdoc=None,
        linked_srcdoc=None,
        source_pane_message=None,
        source_display_url=None,
        linked_display_url=None,
        linked_back_url=None,
        drpid=display_drpid,
        folder_path=folder_path,
        scoreboard_urls_json=json.dumps([n["url"] for n in _scoreboard]),
        show_auto_download=False,
    )


def _page_title_or_h1(page: Any) -> str:
    """Get page <title> or first <h1> text from a Playwright page; empty string if neither."""
    try:
        title = page.title()
        if title and (title or "").strip():
            return (title or "").strip()
        try:
            h1 = page.locator("h1").first.text_content(timeout=2000)
            if h1 and (h1 or "").strip():
                return (h1 or "").strip()
        except Exception:
            pass
    except Exception:
        pass
    return ""


def _unique_pdf_basename(base: str, used: Dict[str, int]) -> str:
    """Return a unique sanitized basename: base.pdf or base_1.pdf, base_2.pdf, etc."""
    safe = sanitize_filename(base, max_length=80)
    if not safe:
        safe = "page"
    key = safe.lower()
    n = used.get(key, 0)
    used[key] = n + 1
    if n == 0:
        return f"{safe}.pdf"
    return f"{safe}_{n}.pdf"


def _generate_save_progress(
    folder_path: Path,
    urls: List[str],
    indices: List[str],
):
    """
    Generator that yields progress lines for the save operation.
    Yields: SAVING\t{url}\t{current}\t{total}\n then DONE\t{count}\n or ERROR\t{msg}\n
    """
    from playwright.sync_api import sync_playwright
    total = len(indices)
    saved: List[str] = []
    used_basenames: Dict[str, int] = {}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for current, idx_str in enumerate(indices, 1):
                try:
                    idx = int(idx_str)
                    if idx < 0 or idx >= len(urls):
                        continue
                    url = urls[idx]
                    if not url or not is_valid_url(url):
                        continue
                    yield f"SAVING\t{url}\t{current}\t{total}\n"
                    page = browser.new_page()
                    try:
                        page.goto(url, wait_until="networkidle", timeout=60000)
                        base = _page_title_or_h1(page)
                        if not base:
                            base = "page"
                        pdf_name = _unique_pdf_basename(base, used_basenames)
                        pdf_path = folder_path / pdf_name
                        page.pdf(path=str(pdf_path))
                        saved.append(pdf_name)
                    finally:
                        page.close()
                except (ValueError, Exception) as e:
                    yield f"ERROR\t{str(e)[:200]}\n"
            browser.close()
    except Exception as e:
        yield f"ERROR\t{str(e)[:200]}\n"
    yield f"DONE\t{len(saved)}\n"


# Progress report interval for large file downloads (MB).
_DOWNLOAD_PROGRESS_INTERVAL_MB = 50.0


def _generate_download_progress(
    url: str,
    folder_path_str: str,
    drpid: int,
    referrer: Optional[str],
):
    """
    Generator that yields progress lines for a single file download.
    Yields: SAVING\\t{basename}\\n, PROGRESS\\t{written}\\t{total}\\n, then DONE\\t{basename}\\t{size}\\t{ext}\\n or ERROR\\t{msg}\\n.
    """
    folder_path = Path(folder_path_str)
    if not folder_path.is_dir():
        yield f"ERROR\tOutput folder not found\n"
        return
    try:
        resp = requests.get(url, stream=True, headers=BROWSER_HEADERS, timeout=(30, 300))
        resp.raise_for_status()
    except requests.RequestException as e:
        yield f"ERROR\t{str(e)[:200]}\n"
        return

    content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    content_disp = resp.headers.get("Content-Disposition")
    content_length: Optional[int] = None
    try:
        cl = resp.headers.get("Content-Length")
        if cl is not None:
            content_length = int(cl)
    except ValueError:
        pass

    filename = _filename_from_content_disposition(content_disp) or _filename_from_url(url)
    ext = _extension_from_content_type(content_type)
    if filename and "." in filename:
        pass  # keep ext from filename
    else:
        if ext and filename:
            filename = filename + (ext if ext.startswith(".") else "." + ext)
        elif ext:
            filename = "download" + (ext if ext.startswith(".") else "." + ext)
    base = filename
    if "." in base:
        base = base.rsplit(".", 1)[0]
        ext_from_name = "." + filename.rsplit(".", 1)[-1]
        if not ext:
            ext = ext_from_name
    else:
        if not ext:
            ext = ""

    used: Dict[str, int] = {p.name.lower(): 1 for p in folder_path.iterdir() if p.is_file()}
    basename = _unique_download_basename(base, ext, used)
    dest = folder_path / basename

    yield f"SAVING\t{basename}\n"
    chunk_size = 1024 * 1024  # 1 MB
    written = 0
    last_yield_mb = 0.0
    try:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                mb = written / (1024 * 1024)
                if (mb - last_yield_mb) >= _DOWNLOAD_PROGRESS_INTERVAL_MB or (content_length and written >= content_length):
                    last_yield_mb = mb
                    total_str = str(content_length) if content_length is not None else ""
                    yield f"PROGRESS\t{written}\t{total_str}\n"
    except OSError as e:
        yield f"ERROR\t{str(e)[:200]}\n"
        return

    ext_display = ext.lstrip(".")
    yield f"DONE\t{basename}\t{written}\t{ext_display}\n"

    _result_by_drpid.setdefault(drpid, {}).setdefault("downloads", []).append({
        "url": url,
        "path": str(dest),
        "size": written,
        "extension": ext_display,
        "filename": basename,
    })
    _scoreboard_add_download(url, referrer, str(dest), written, ext_display, filename=basename)


@app.route("/download-file", methods=["POST"])
def download_file() -> Any:
    """
    Download a non-HTML URL to the project output folder; streams progress (SAVING, PROGRESS, DONE).
    Expects url, drpid, referrer (optional). Uses folder_path from _result_by_drpid.
    """
    url = (request.form.get("url") or "").strip()
    drpid_str = (request.form.get("drpid") or "").strip()
    referrer = (request.form.get("referrer") or "").strip() or None

    if not url or not is_valid_url(url):
        return "Invalid URL", 400
    try:
        drpid = int(drpid_str)
    except (ValueError, TypeError):
        return "Invalid DRPID", 400

    folder_path = _result_by_drpid.get(drpid, {}).get("folder_path")
    if not folder_path:
        return "No output folder for this project", 400

    def stream() -> Any:
        for line in _generate_download_progress(url, folder_path, drpid, referrer):
            yield line

    from flask import Response
    return Response(
        stream(),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.route("/save", methods=["POST"])
def save() -> Any:
    """
    Save checked scoreboard pages as PDFs; streams progress (SAVING url n/t, DONE count).
    Expects folder_path, scoreboard_urls_json, and save_url (list of indices).
    """
    folder_path_str = (request.form.get("folder_path") or "").strip()
    urls_json = (request.form.get("scoreboard_urls_json") or "[]").strip()
    indices = request.form.getlist("save_url")

    if not folder_path_str or not indices:
        return redirect(url_for("index"))

    try:
        urls = json.loads(urls_json)
    except json.JSONDecodeError:
        return redirect(url_for("index"))

    folder_path = Path(folder_path_str)
    if not folder_path.is_dir():
        return redirect(url_for("index"))

    drpid_val: Optional[int] = None
    try:
        drpid_val = int((request.form.get("drpid") or "").strip())
    except (ValueError, TypeError):
        pass

    def stream() -> Any:
        for line in _generate_save_progress(folder_path, urls, indices, drpid=drpid_val):
            yield line

    from flask import Response
    return Response(
        stream(),
        mimetype="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
