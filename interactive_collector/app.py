"""
Flask app for Interactive Collector.

Multi-pane layout: scoreboard (left), Source pane, Linked pane.
Links open in the Linked pane so you can see where you came from.
"""

import html
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

from flask import Flask, request, render_template_string

from utils.url_utils import is_valid_url, fetch_page_body, resolve_catalog_resource_url

app = Flask(__name__)

# In-memory scoreboard: list of {url, referrer, status_label}. Referrer None = root.
_scoreboard: List[Dict[str, Any]] = []

_INDEX_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Interactive Collector</title>
<style>
  body { margin: 0; font-family: sans-serif; }
  .top { padding: 8px; background: #eee; border-bottom: 1px solid #ccc; }
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
  .panes { flex: 1; display: flex; flex-direction: row; min-width: 0; }
  .pane { flex: 1; min-width: 120px; min-height: 0; border: 1px solid #ccc; margin: 4px; display: flex; flex-direction: column; overflow: hidden; }
  .pane.source-pane { resize: horizontal; max-width: 80%; }
  .pane-header { padding: 4px 8px; background: #e8e8e8; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pane-header-label { font-weight: bold; }
  .pane-header-url { font-weight: normal; }
  .pane-iframe { flex: 1; width: 100%; border: none; min-height: 200px; }
  .pane-empty { flex: 1; padding: 16px; color: #666; font-size: 14px; }
</style>
</head>
<body>
  <div class="top">
    <form method="get" action="/">
      <label for="url">URL:</label>
      <input type="url" id="url" name="url" value="{{ initial_url or '' }}" size="60" placeholder="https://example.com" />
      <button type="submit">Go</button>
    </form>
  </div>
  <div class="main">
    <div class="scoreboard">
      <h3>Scoreboard</h3>
      {{ scoreboard_html | safe }}
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
        <div class="pane-header" title="{{ (linked_display_url or '') | e }}"><span class="pane-header-label">Linked:</span> <span class="pane-header-url">{{ (linked_display_url or '—') | e }}</span></div>
        {% if linked_srcdoc %}
        <iframe name="linked" class="pane-iframe" srcdoc="{{ linked_srcdoc | safe }}" sandbox="allow-same-origin allow-scripts allow-forms allow-top-navigation-by-user-activation" title="Linked page"></iframe>
        {% else %}
        <div class="pane-empty">Click a link in Source (or Linked) to open it here.</div>
        {% endif %}
      </div>
    </div>
  </div>
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
) -> str:
    """
    Rewrite <a href="..."> so clicks load in the Linked pane. Builds
    ?source_url=...&linked_url=...&referrer=... so the new page opens in Linked
    and both panes are re-rendered. Only rewrites http/https links.
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


def _scoreboard_tree() -> List[Dict[str, Any]]:
    """Return scoreboard as a tree. One node per entry (no merging by URL) so original stays OK, dupes shown separately."""
    nodes = [
        {"url": n["url"], "referrer": n["referrer"], "status_label": n["status_label"], "is_dupe": n.get("is_dupe", False), "children": []}
        for n in _scoreboard
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


def _scoreboard_render_html(app_root: str, current_source_url: str) -> str:
    """Render scoreboard tree as HTML (nested ul). Checkbox checked for original source and OK non-dupes."""
    roots = _scoreboard_tree()
    if not roots:
        return "<p><em>No pages yet.</em></p>"

    original_source_url = next((n["url"] for n in _scoreboard if n.get("referrer") is None), _scoreboard[0]["url"] if _scoreboard else "")

    def render_node(node: Dict[str, Any]) -> str:
        url = node["url"]
        url_short = url[:80] + ("..." if len(url) > 80 else "")
        status = node["status_label"]
        is_dupe = node.get("is_dupe", False)
        status_display = status + " (dupe)" if is_dupe else status
        status_class = "status-404" if "404" in status else "status-ok"
        referrer = node.get("referrer") or current_source_url
        is_ok = "OK" in status
        checked = (url == original_source_url and is_ok) or (is_ok and not is_dupe)
        cb = f'<input type="checkbox" class="scoreboard-cb" {"checked" if checked else ""} />'
        if current_source_url:
            params = f"source_url={quote(current_source_url)}&linked_url={quote(url)}&referrer={quote(referrer)}&from_scoreboard=1"
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
        body_with_base, url_param, app_root, source_url, url_param
    )
    safe_srcdoc = body_rewritten.replace("&", "&amp;").replace('"', "&quot;")
    return safe_srcdoc, None, status_label


@app.route("/")
def index() -> str:
    """
    Three-pane layout: scoreboard, Source, Linked.

    Initial: ?url=... -> fetch url, show in Source; add root to scoreboard.
    Link click: ?source_url=...&linked_url=...&referrer=... -> fetch both, show in Source and Linked;
    add (linked_url, referrer) to scoreboard.
    """
    app_root = request.url_root.rstrip("/") or request.host_url.rstrip("/")
    url_param = request.args.get("url", "").strip()
    source_url_param = request.args.get("source_url", "").strip()
    linked_url_param = request.args.get("linked_url", "").strip()
    referrer_param = request.args.get("referrer", "").strip()
    from_scoreboard = request.args.get("from_scoreboard", "").strip()

    # Initial load: single url=
    if url_param and not source_url_param and not linked_url_param:
        _scoreboard.clear()
        if not is_valid_url(url_param):
            return render_template_string(
                _INDEX_HTML,
                initial_url=html.escape(url_param),
                scoreboard_html=_scoreboard_render_html(app_root, ""),
                source_srcdoc=None,
                linked_srcdoc=None,
                source_pane_message="Invalid URL. Provide a valid http:// or https:// URL.",
                source_display_url=None,
                linked_display_url=None,
            )
        safe_srcdoc, body_message, status_label = _prepare_pane_content(
            url_param, app_root, url_param
        )
        _scoreboard_add(url_param, None, status_label)
        source_srcdoc = safe_srcdoc if body_message is None else None
        if body_message and safe_srcdoc is None:
            source_srcdoc = None
        return render_template_string(
            _INDEX_HTML,
            initial_url=html.escape(url_param),
            scoreboard_html=_scoreboard_render_html(app_root, url_param),
            source_srcdoc=source_srcdoc,
            linked_srcdoc=None,
            source_pane_message=body_message,
            source_display_url=url_param,
            linked_display_url=None,
        )

    # Link click: source_url + linked_url + referrer
    if source_url_param and linked_url_param and referrer_param:
        if not is_valid_url(source_url_param) or not is_valid_url(linked_url_param):
            return render_template_string(
                _INDEX_HTML,
                initial_url=html.escape(source_url_param),
                scoreboard_html=_scoreboard_render_html(app_root, source_url_param),
                source_srcdoc=None,
                linked_srcdoc=None,
                source_pane_message=None,
                source_display_url=None,
                linked_display_url=None,
            )
        # Fetch both panes. For catalog.data.gov links, resolve on click and show the resolved URL in the Linked pane (skip the relay).
        src_srcdoc, _, src_status = _prepare_pane_content(
            source_url_param, app_root, source_url_param
        )
        linked_url_for_fetch = linked_url_param
        linked_display_url = linked_url_param
        resolved_linked: Optional[str] = None
        if linked_url_param.startswith("https://catalog.data.gov"):
            resolved_linked = resolve_catalog_resource_url(linked_url_param)
            if resolved_linked:
                linked_url_for_fetch = resolved_linked
                linked_display_url = resolved_linked
        linked_srcdoc, _, linked_status = _prepare_pane_content(
            linked_url_for_fetch, app_root, source_url_param
        )
        if not any(n["url"] == source_url_param for n in _scoreboard):
            _scoreboard_add(source_url_param, None, src_status)
        if not from_scoreboard:
            if resolved_linked:
                _scoreboard_add(resolved_linked, referrer_param, linked_status)
            elif not linked_url_param.startswith("https://catalog.data.gov"):
                _scoreboard_add(linked_url_param, referrer_param, linked_status)
        # else: from_scoreboard click — don't add new entry or check dupe
        return render_template_string(
            _INDEX_HTML,
            initial_url=html.escape(source_url_param),
            scoreboard_html=_scoreboard_render_html(app_root, source_url_param),
            source_srcdoc=src_srcdoc,
            linked_srcdoc=linked_srcdoc,
            source_display_url=source_url_param,
            linked_display_url=linked_display_url,
        )

    # No URL: show form and empty panes
    return render_template_string(
        _INDEX_HTML,
        initial_url="",
        scoreboard_html=_scoreboard_render_html(app_root, ""),
        source_srcdoc=None,
        linked_srcdoc=None,
        source_pane_message=None,
        source_display_url=None,
        linked_display_url=None,
    )
