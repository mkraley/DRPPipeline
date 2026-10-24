"""Save the FERC EQR explanation page as a rendered PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from collectors.EqrProjectRange import EXPLAIN_URL
from collectors.FercCollectedFiles import LANDING_PDF_NAME

_INTERSTITIAL_MARKERS = (
    "performing security verification",
    "just a moment",
    "cf-browser-verification",
    "checking your browser",
)
FetchHtml = Callable[[], str]


def pdf_is_security_interstitial(path: Path) -> bool:
    """Return True when a saved PDF is the browser security check."""
    if not path.is_file():
        return False
    text = path.read_bytes().decode("latin-1", errors="ignore").lower()
    return any(marker in text for marker in _INTERSTITIAL_MARKERS)


def save_explanation_pdf(
    pages: Any,
    folder: Path,
    html: str | None,
    fetch_html: FetchHtml,
    *,
    replace_existing: bool = False,
) -> None:
    """
    Write ``landing_page.pdf`` from the live explanation page.

    The browser loads the page's stylesheets, scripts, and images. A security
    check captured by an earlier print is replaced.

    Args:
        pages: Renderer with ``url_html_to_pdf``.
        folder: Project folder.
        html: Explanation HTML already in hand, or None to fetch it.
        fetch_html: Callable used when ``html`` is omitted.
        replace_existing: When True, print again even if a PDF is already there.

    Raises:
        ValueError: When the HTML is a security check or the PDF is not written.
    """
    dest = folder / LANDING_PDF_NAME
    if _keep_existing(dest, replace_existing):
        return
    page_html = html if html is not None else fetch_html()
    if is_security_interstitial(page_html):
        raise ValueError("FERC returned a security check instead of the EQR page")
    if not pages.url_html_to_pdf(EXPLAIN_URL, page_html, dest):
        raise ValueError("Failed to save the EQR explanation PDF")


def is_security_interstitial(html: str) -> bool:
    """Return True when ``html`` is a browser security check rather than the article."""
    lowered = html.lower()
    if "electric quarterly" in lowered:
        return False
    return any(marker in lowered for marker in _INTERSTITIAL_MARKERS)


def _keep_existing(path: Path, replace_existing: bool) -> bool:
    """Return True when the current PDF should be left in place."""
    if replace_existing or not path.is_file() or path.stat().st_size <= 0:
        return False
    return not pdf_is_security_interstitial(path)
