"""Browser session for NRC pages that reject plain HTTP clients."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.event_notification_links import looks_like_event_report

_REPORT_PRINT_CSS = """
html, body {
    overflow: visible !important;
    height: auto !important;
    background-image: none !important;
    background-color: #0d1225 !important;
}
header, footer, nav, .usa-banner, .alert-banner-container,
.usa-layout-docs__sidenav, .breadcrumb, .pager, .usa-overlay {
    display: none !important;
}
.grid, .grid-row, .grid-container, .grid.border, .usa-layout-docs__main {
    display: block !important;
}
main, .nrc-event-report-day, .grid, .grid-row, .grid-container,
.grid.border, .usa-layout-docs__main, h1, p, div {
    background-color: #0d1225 !important;
    color: #f2f2f2 !important;
    -webkit-box-decoration-break: clone;
    box-decoration-break: clone;
}
.th {
    background-color: #eaf2eb !important;
    color: #333333 !important;
}
"""

_STRIP_INTERACTIVE_JS = """
() => {
  document.querySelectorAll('input, select, textarea, button').forEach(el => el.remove());
  document.querySelectorAll('a').forEach(anchor => {
    const span = document.createElement('span');
    span.innerHTML = anchor.innerHTML;
    anchor.replaceWith(span);
  });
}
"""


class EventNotificationBrowser:
    """
    Load NRC HTML with Chromium and print a day page to PDF.

    Plain HTTP requests receive Akamai 403. Visiting pages in one browser
    session is the path that returns the report.
    """

    def __init__(self, headless: bool = True) -> None:
        """Store whether Chromium should run without a window."""
        self._headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    def __enter__(self) -> EventNotificationBrowser:
        """Launch Chromium and return this session."""
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._page = self._browser.new_page()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close the browser even when a page load failed."""
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def fetch(self, url: str) -> str:
        """Return the HTML of ``url``. Raises when the response is not HTTP 200."""
        self._open(url)
        return self._page.content()

    def save_pdf(self, url: str, dest: Path) -> None:
        """Print the rendered report at ``url`` to ``dest``, without site chrome."""
        self._open(url)
        if not looks_like_event_report(self._page.content()):
            raise RuntimeError(f"Page is not an event notification report: {url}")
        self._prepare_report_for_pdf()
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._page.pdf(
            path=str(dest),
            format="Letter",
            print_background=True,
            margin={"top": "0.6in", "bottom": "0.6in", "left": "0.6in", "right": "0.6in"},
        )
        if not dest.is_file() or dest.stat().st_size == 0:
            raise RuntimeError(f"Empty PDF for {url}")

    def _prepare_report_for_pdf(self) -> None:
        """Give each page a solid background and drop form controls."""
        self._page.add_style_tag(content=_REPORT_PRINT_CSS)
        self._page.evaluate(_STRIP_INTERACTIVE_JS)

    def _open(self, url: str) -> None:
        """Navigate to ``url`` and require HTTP 200."""
        response = self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        status = response.status if response is not None else 0
        if status != 200:
            raise RuntimeError(f"HTTP {status} for {url}")
