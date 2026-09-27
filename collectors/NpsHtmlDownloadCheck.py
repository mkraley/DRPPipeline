"""
Detect IRMA DownloadFile responses that are HTML pages instead of the file.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HTML_MARKERS = (b"<html", b"<!doctype html")
_ALLOWED_HTML_SUFFIXES = frozenset({".html", ".htm", ".xhtml", ".rhtml", ".shtml"})
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_IRMA_HOME = "https://irma.nps.gov/datastore"


def is_allowed_html_filename(filename: str) -> bool:
    """Return True when the Digital File is itself an HTML document."""
    suffix = Path(filename).suffix.lower()
    return suffix in _ALLOWED_HTML_SUFFIXES


def unexpected_html_message(
    path: Path,
    *,
    filename: str,
    url: str,
    status_code: int | None = None,
    content_type: str = "",
    final_url: str = "",
) -> str | None:
    """
    Return a diagnostic when ``path`` is an HTML page rather than ``filename``.

    Legitimate HTML Digital Files (``.html``, ``.rhtml``, …) return None.
    """
    if is_allowed_html_filename(filename):
        return None
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
        head = path.read_bytes()[:800]
    except OSError:
        return None
    type_html = "html" in (content_type or "").lower()
    body_html = any(marker in head.lower() for marker in _HTML_MARKERS)
    if not type_html and not body_html:
        return None
    return _format_html_message(
        filename=filename,
        url=url,
        status_code=status_code,
        content_type=content_type,
        final_url=final_url,
        size=size,
        head=head,
    )


def _format_html_message(
    *,
    filename: str,
    url: str,
    status_code: int | None,
    content_type: str,
    final_url: str,
    size: int,
    head: bytes,
) -> str:
    """Build one error/warning line describing an HTML DownloadFile body."""
    parts = [f"Download returned HTML: {filename}"]
    if status_code is not None:
        parts.append(f"HTTP {status_code}")
    if content_type:
        parts.append(content_type.split(";")[0].strip())
    landing = (final_url or "").strip()
    if landing and landing.rstrip("/") != url.rstrip("/"):
        parts.append(f"redirected to {landing}")
        if _looks_like_irma_home(landing):
            parts.append("IRMA home/app page")
    title = _html_title(head)
    if title:
        parts.append(f"title {title!r}")
    parts.append(f"{size} bytes")
    parts.append(url)
    return " | ".join(parts)


def _html_title(head: bytes) -> str:
    """Return a short ``<title>`` from the first bytes of a body."""
    text = head.decode("utf-8", errors="replace")
    match = _TITLE_RE.search(text)
    if not match:
        return ""
    title = " ".join(match.group(1).split())
    return title[:120]


def _looks_like_irma_home(url: str) -> bool:
    """Return True when a redirect landed on the DataStore app, not DownloadFile."""
    lowered = url.strip().lower().rstrip("/")
    if "downloadfile" in lowered:
        return False
    return lowered.startswith(_IRMA_HOME) or lowered.rstrip("/") == "https://irma.nps.gov"


def response_meta(response: Any) -> dict[str, Any]:
    """Copy status, Content-Type, and final URL from a ``requests.Response``."""
    headers = getattr(response, "headers", {}) or {}
    return {
        "status_code": getattr(response, "status_code", None),
        "content_type": str(headers.get("Content-Type") or ""),
        "final_url": str(getattr(response, "url", "") or ""),
    }
