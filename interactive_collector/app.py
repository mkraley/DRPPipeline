"""
Flask app for Interactive Collector.

Phase 1: Single route to fetch a URL and display status and body.
"""

import html
from typing import Optional

from flask import Flask, request, render_template_string

from utils.url_utils import is_valid_url, fetch_page_body

app = Flask(__name__)

_INDEX_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Interactive Collector</title></head>
<body>
  <h1>Interactive Collector</h1>
  <form method="get" action="/">
    <label for="url">URL:</label>
    <input type="url" id="url" name="url" size="60" placeholder="https://example.com" />
    <button type="submit">Fetch</button>
  </form>
  {% if result %}
  <h2>Result</h2>
  <p><strong>URL:</strong> {{ result.url }}</p>
  <p><strong>Status:</strong> {{ result.status_label }}</p>
  <p><strong>Content-Type:</strong> {{ result.content_type or "—" }}</p>
  {% if result.body_message %}
  <p>{{ result.body_message }}</p>
  {% else %}
  <iframe srcdoc="{{ result.safe_srcdoc | safe }}" style="border:1px solid #ccc; width:100%; height:70vh;" sandbox="allow-same-origin" title="Fetched page"></iframe>
  {% endif %}
  {% endif %}
</body>
</html>
"""


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


def _status_label(status_code: int, is_logical_404: bool) -> str:
    """Return human-readable status for display."""
    if status_code == 404:
        return "404 (logical)" if is_logical_404 else "404"
    if status_code == 200:
        return "OK"
    if status_code < 0:
        return f"Error ({status_code})"
    return str(status_code)


@app.route("/")
def index() -> str:
    """
    Show URL form or fetch the given URL and display result.

    Query param `url`: when present and valid, fetches the URL and displays
    status (OK / 404 / 404 logical) and body. Otherwise shows the form only.
    """
    url_param: Optional[str] = request.args.get("url", "").strip()
    if not url_param:
        return render_template_string(_INDEX_HTML, result=None)

    if not is_valid_url(url_param):
        return render_template_string(
            _INDEX_HTML,
            result={
                "url": html.escape(url_param),
                "status_label": "Invalid URL",
                "content_type": None,
                "body_message": "Provide a valid http:// or https:// URL.",
                "safe_srcdoc": "",
            },
        )

    status_code, body, content_type, is_logical_404 = fetch_page_body(url_param)
    status_label = _status_label(status_code, is_logical_404)

    if not _is_displayable_text(content_type) and content_type:
        body_message = f"Binary content ({html.escape(content_type)}). Not displayed."
        safe_srcdoc = ""
    elif (body or "").strip() == "" and _is_displayable_text(content_type):
        body_message = "Content could not be displayed (possibly binary or wrong encoding)."
        safe_srcdoc = ""
    else:
        body_message = None
        # Escape for safe use inside srcdoc="..." attribute (don't escape < > so iframe renders HTML)
        safe_srcdoc = (body or "").replace("&", "&amp;").replace('"', "&quot;")

    return render_template_string(
        _INDEX_HTML,
        result={
            "url": html.escape(url_param),
            "status_label": status_label,
            "content_type": content_type or "—",
            "safe_srcdoc": safe_srcdoc,
            "body_message": body_message,
        },
    )
