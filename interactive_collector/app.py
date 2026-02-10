"""
Flask app for Interactive Collector.

Phase 1: Single route to fetch a URL and display status and body.
"""

import html
import re
from typing import Optional
from urllib.parse import quote, urljoin

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
  <iframe srcdoc="{{ result.safe_srcdoc | safe }}" style="border:1px solid #ccc; width:100%; height:70vh;" sandbox="allow-same-origin allow-scripts" title="Fetched page"></iframe>
  {% endif %}
  {% endif %}
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


def _rewrite_links_to_app(html_body: str, page_url: str, app_root_url: str) -> str:
    """
    Rewrite <a href="..."> only (not <link> or others) to point at our app so clicks don't
    load external sites in the iframe (X-Frame-Options). Leaves link/script href/src unchanged
    so CSS/JS still load from the original server.
    """
    # Match only <a ...> opening tags so we don't rewrite <link href="..."> etc.
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
        app_url = app_root_url.rstrip("/") + "/?url=" + quote(absolute_url, safe="")
        escaped = app_url.replace("&", "&amp;").replace('"', "&quot;")
        return f"<a {before_href} target=\"_top\" href={quote_char}{escaped}{quote_char} {after_href}>"

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
        # Inject <base href> so relative CSS/JS/images load from the fetched page's origin
        body_with_base = _inject_base_into_html(body or "", url_param)
        # Rewrite links to go through our app so the iframe doesn't load external URLs (X-Frame-Options)
        app_root = request.url_root.rstrip("/") or request.host_url.rstrip("/")
        body_rewritten = _rewrite_links_to_app(body_with_base, url_param, app_root)
        # Escape for safe use inside srcdoc="..." attribute (don't escape < > so iframe renders HTML)
        safe_srcdoc = body_rewritten.replace("&", "&amp;").replace('"', "&quot;")

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
