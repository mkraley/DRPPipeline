"""
API module for page loading and HTML preparation.

Fetches URLs, injects base tag for relative resource resolution, and for SPA mode
injects a link-interceptor script that posts COLLECTOR_LINK_CLICK to the parent
on link clicks so the React app can load pages via API without full navigation.
Resolves catalog.data.gov links to direct resource URLs.
"""

import html
import re
from typing import Any, Optional
from urllib.parse import urljoin

from utils.url_utils import fetch_page_body, is_valid_url, is_waf_challenge, resolve_catalog_resource_url

# Content types we display as text (not binary). XML is excluded so it's offered as download.
_DISPLAYABLE = (
    "application/json",
    "application/javascript",
    "application/xhtml+xml",
    "text/plain",
)


def _base_url_for_page(page_url: str) -> str:
    """Return the base URL (directory) for resolving relative URLs on the page."""
    if page_url.endswith("/"):
        return page_url
    return urljoin(page_url + "/", "..")


def _inject_base(html_body: str, page_url: str) -> str:
    """
    Inject <base href="..."> so relative CSS/JS/images load in the iframe.

    Tries: (1) inside first <head>; (2) after <html> as new <head>; (3) prepend at start.
    """
    base_href = _base_url_for_page(page_url)
    if not base_href.endswith("/"):
        base_href = base_href + "/"
    base_escaped = base_href.replace("&", "&amp;").replace('"', "&quot;")
    base_tag = f'<base href="{base_escaped}">'

    # (1) Inject into existing <head>
    with_head = re.sub(r"(<head[^>]*>)", r"\1" + base_tag, html_body, count=1, flags=re.IGNORECASE)
    if with_head != html_body:
        return with_head

    # (2) No <head>: insert <head><base...></head> after <html>
    with_html_head = re.sub(
        r"(<html[^>]*>)",
        r"\1<head>" + base_tag + "</head>",
        html_body,
        count=1,
        flags=re.IGNORECASE,
    )
    if with_html_head != html_body:
        return with_html_head

    # (3) No <html>: prepend base at start so relative URLs still resolve
    return base_tag + html_body


def _is_displayable_text(content_type: Optional[str]) -> bool:
    """Return True if we should show the response body as text (not binary)."""
    if not content_type:
        return True
    ct = content_type.lower().strip()
    # XML types: treat as binary so we offer download instead of iframe
    if ct in ("application/xml", "text/xml"):
        return False
    if ct.startswith("text/"):
        return True
    if ct in _DISPLAYABLE:
        return True
    return False


def _body_looks_like_xml(body: Any) -> bool:
    """Return True if body starts with XML declaration (e.g. when Content-Type is wrong)."""
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    s = (body or "").strip()
    if len(s) < 5:
        return False
    return s[:5].lower() == "<?xml"


def _body_looks_like_html(body: Any) -> bool:
    """
    Return True if the body looks like an HTML document (not data XML).

    Pages like NCBI BioSample may be served as application/xml or with <?xml
    but are actually HTML. We treat as HTML if we see <!DOCTYPE html or <html
    in the first 8KB so they display in the pane instead of as download.
    """
    if body is None:
        return False
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    s = (body or "").strip()
    if len(s) < 4:
        return False
    head = s[:8192].lower()
    return "<!doctype html" in head or "<html" in head


def _h1_from_html(html_body: Any) -> str:
    """Extract text of the first <h1> in the HTML; empty string if none."""
    if isinstance(html_body, bytes):
        html_body = html_body.decode("utf-8", errors="replace")
    if not (html_body or "").strip():
        return ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html_body, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    inner = m.group(1).strip()
    inner = re.sub(r"<[^>]+>", "", inner)
    return (inner or "").strip()


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags from text and normalize whitespace."""
    out = re.sub(r"<[^>]+>", "", text)
    return " ".join((out or "").split())


def _extract_metadata_from_html(html_body: Any) -> dict[str, str]:
    """
    Extract metadata from page HTML for preloading.
    Returns dict with title, agency, office, keywords (empty string if not found).
    - title: h1 with itemprop="name"
    - agency: section#organization-info h1.heading
    - office: a with title="publisher" (link text)
    - keywords: text content of section.tags, semicolon delimited
    """
    result: dict[str, str] = {"title": "", "agency": "", "office": "", "keywords": ""}
    if isinstance(html_body, bytes):
        html_body = html_body.decode("utf-8", errors="replace")
    body = (html_body or "").strip()
    if not body:
        return result
    # title: h1 with itemprop="name"
    m = re.search(
        r'<h1[^>]*itemprop\s*=\s*["\']name["\'][^>]*>(.*?)</h1>',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        result["title"] = _strip_html_tags(m.group(1))
    # agency: section#organization-info, then h1.heading
    m = re.search(
        r'<section[^>]*id\s*=\s*["\']organization-info["\'][^>]*>.*?<h1[^>]*class\s*=\s*["\'][^"\']*\bheading\b[^"\']*["\'][^>]*>(.*?)</h1>',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        result["agency"] = _strip_html_tags(m.group(1))
    # office: a with title="publisher"
    m = re.search(
        r'<a[^>]*title\s*=\s*["\']publisher["\'][^>]*>(.*?)</a>',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        result["office"] = _strip_html_tags(m.group(1))
    # keywords: section.tags text content, semicolon delimited
    # Replace space with "; " only if no semicolons already present
    m = re.search(
        r'<section[^>]*class\s*=\s*["\'][^"\']*\btags\b[^"\']*["\'][^>]*>(.*?)</section>',
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        raw = _strip_html_tags(m.group(1))
        if ";" in raw:
            parts = [p.strip() for p in raw.split(";") if p.strip()]
            result["keywords"] = "; ".join(parts)
        else:
            parts = [p.strip() for p in raw.split() if p.strip()]
            result["keywords"] = "; ".join(parts)
    return result


def _status_label(status_code: int, is_logical_404: bool) -> str:
    """Return human-readable status for display."""
    if status_code == 404:
        return "404 (logical)" if is_logical_404 else "404"
    if status_code == 200:
        return "OK"
    if status_code < 0:
        return f"Error ({status_code})"
    return str(status_code)


def _inject_link_interceptor(html_body: str, page_url: str) -> str:
    """
    Inject a script that intercepts link clicks and posts COLLECTOR_LINK_CLICK to parent.

    For SPA: links no longer navigate; the React app receives the message and loads
    the page via API, updating only the Linked pane.
    """
    import json as _json
    page_url_js = _json.dumps(page_url)
    script = f'''<script>
(function(){{
  var pageUrl = {page_url_js};
  document.addEventListener("click", function(e) {{
    var a = e.target && (e.target.closest ? e.target.closest("a") : e.target);
    if (!a || !a.href) return;
    if (a.href.startsWith("javascript:") || a.href.startsWith("mailto:") || a.href.startsWith("tel:") || a.href.startsWith("#")) return;
    if (!a.href.startsWith("http://") && !a.href.startsWith("https://")) return;
    e.preventDefault();
    e.stopPropagation();
    window.parent.postMessage({{ type: "COLLECTOR_LINK_CLICK", url: a.href, referrer: pageUrl }}, "*");
  }}, true);
}})();
</script>'''
    # Insert before </body> or at end if no body
    if "</body>" in html_body.lower():
        return re.sub(r"</body>", script + "</body>", html_body, count=1, flags=re.IGNORECASE)
    return html_body + script


def prepare_page_content(
    url_param: str,
    source_url: str,
    drpid: Optional[str] = None,
    for_spa: bool = True,
) -> tuple[Optional[str], Optional[str], str, str, dict[str, str]]:
    """
    Fetch URL, inject base, and link interceptor; return (srcdoc, message, status, h1, extracted).

    Args:
        url_param: URL to fetch.
        source_url: Source pane URL (for catalog resolution context).
        drpid: Optional DRPID for display.
        for_spa: If True, inject link interceptor for SPA mode.

    Returns:
        (srcdoc, body_message, status_label, h1_text, extracted_metadata)
        - srcdoc: HTML for iframe srcdoc, or None if binary/unusable.
        - body_message: Error/notice string if srcdoc is None.
        - status_label: "OK", "404", etc.
        - h1_text: First <h1> text.
        - extracted_metadata: dict with title, agency, office from page HTML.
    """
    status_code, body, content_type, is_logical_404 = fetch_page_body(url_param)
    status_label = _status_label(status_code, is_logical_404)
    h1_text = _h1_from_html(body or "") if body else ""
    extracted = _extract_metadata_from_html(body) if body else {"title": "", "agency": "", "office": "", "keywords": ""}

    # catalog.data.gov uses AWS WAF; when blocked, we get a challenge page instead of real content.
    # Show a helpful message instead of the raw challenge HTML ("JavaScript is disabled").
    if is_waf_challenge(status_code, body or ""):
        return (
            None,
            "This page requires browser verification (catalog.data.gov uses AWS WAF). "
            "Click 'Open' above to view it in your browser, or try again later.",
            "WAF challenge",
            "",
            extracted,
        )

    # If body is actually HTML (e.g. NCBI pages served as XML), display it
    if _body_looks_like_html(body):
        pass  # treat as displayable below
    elif not _is_displayable_text(content_type) and content_type:
        return None, f"Binary content ({html.escape(content_type)}). Not displayed.", status_label, "", extracted
    elif _body_looks_like_xml(body):
        return None, "XML content. Not displayed.", status_label, "", extracted
    if (body or "").strip() == "" and _is_displayable_text(content_type):
        return None, "Content could not be displayed (possibly binary or wrong encoding).", status_label, "", extracted

    body_with_base = _inject_base(body or "", url_param)
    if for_spa:
        body_final = _inject_link_interceptor(body_with_base, url_param)
    else:
        body_final = body_with_base
    return body_final, None, status_label, h1_text, extracted


def load_page(
    url: str,
    referrer: Optional[str],
    source_url: str,
    drpid: Optional[str],
    from_scoreboard: bool,
    app_root: str,
) -> dict:
    """
    Load a page for the Linked pane. Resolves catalog URLs, fetches, adds to scoreboard.

    Args:
        url: URL to load.
        referrer: URL of the page containing the link.
        source_url: Current source pane URL.
        drpid: Optional DRPID.
        from_scoreboard: If True, don't add to scoreboard (user clicked scoreboard link).
        app_root: App base URL (for any legacy links).

    Returns:
        Dict with srcdoc, status_label, h1_text, is_binary, linked_display_url,
        scoreboard (tree), scoreboard_urls (flat list).
    """
    from interactive_collector.api_scoreboard import add_to_scoreboard, get_scoreboard_tree, has_url
    from interactive_collector.api_projects import ensure_output_folder, folder_path_for_drpid

    if not is_valid_url(url):
        return {
            "error": "Invalid URL",
            "srcdoc": None,
            "status_label": "Error",
            "is_binary": False,
        }

    linked_url_for_fetch = url
    linked_display_url = url
    # Resolve catalog.data.gov links to direct resource URL (avoids redirect chain).
    if url.startswith("https://catalog.data.gov"):
        resolved = resolve_catalog_resource_url(url)
        if resolved:
            linked_url_for_fetch = resolved
            linked_display_url = resolved

    srcdoc, body_message, status_label, h1_text, extracted = prepare_page_content(
        linked_url_for_fetch, source_url, drpid, for_spa=True
    )
    linked_is_binary = srcdoc is None and body_message and (
        "Binary content" in (body_message or "") or "XML content" in (body_message or "")
    )

    # Add source to scoreboard if not present (when loading linked from source).
    source_in_board = has_url(source_url)
    if not source_in_board and source_url:
        add_to_scoreboard(source_url, None, "OK")  # Assume OK; could fetch to verify

    if not from_scoreboard and not linked_is_binary:
        title = (extracted.get("title", "") or h1_text or "").strip() or None
        add_to_scoreboard(linked_url_for_fetch, referrer or source_url, status_label, title)

    # Ensure folder for drpid when we have one.
    display_drpid = drpid
    folder_path = folder_path_for_drpid(display_drpid)
    if folder_path is None and display_drpid:
        try:
            folder_path = ensure_output_folder(int(display_drpid))
        except (ValueError, TypeError):
            pass

    # When binary (PDF, ZIP, etc.), show referrer page in Linked pane instead of raw binary.
    linked_srcdoc_for_display = srcdoc
    if linked_is_binary and referrer and is_valid_url(referrer):
        ref_srcdoc, _, _, _, _ = prepare_page_content(
            referrer, source_url, drpid, for_spa=True
        )
        if ref_srcdoc:
            linked_srcdoc_for_display = ref_srcdoc
            linked_display_url = referrer
    elif linked_is_binary:
        # Show source in linked pane when binary and no valid referrer.
        if source_url and is_valid_url(source_url):
            ref_srcdoc, _, _, _, _ = prepare_page_content(
                source_url, source_url, drpid, for_spa=True
            )
            if ref_srcdoc:
                linked_srcdoc_for_display = ref_srcdoc
                linked_display_url = source_url

    from interactive_collector.api_scoreboard import get_scoreboard_urls

    tree = get_scoreboard_tree()
    urls = get_scoreboard_urls()

    return {
        "srcdoc": linked_srcdoc_for_display,
        "status_label": status_label,
        "h1_text": _h1_from_html(body_message or "") if body_message else "",
        "is_binary": linked_is_binary,
        "linked_display_url": linked_display_url,
        "linked_binary_url": linked_url_for_fetch if linked_is_binary else None,
        "body_message": body_message,
        "scoreboard": tree,
        "scoreboard_urls": urls,
        "folder_path": folder_path,
    }
