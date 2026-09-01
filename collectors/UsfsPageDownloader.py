"""Playwright helper to render USFS web pages as PDF."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Optional, Tuple

from collectors.PlaywrightSession import PlaywrightSession
from utils.Logger import Logger
from utils.url_utils import _fetch_html_with_playwright_page

_NAVIGATION_WAIT = "commit"
_NAVIGATION_TIMEOUT_MS = 30000
_SETTLE_MS = 3000
_LOAD_TIMEOUT_MS = 35000
_PRINT_TIMEOUT_MS = 90000
_FILE_DOWNLOAD_TIMEOUT_MS = 3600 * 1000
_CONTENT_LENGTH_TIMEOUT_MS = 30_000


class UsfsPageDownloader:
    """Render USFS catalog pages in Chromium and save as PDF."""

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize the page downloader.

        Args:
            headless: Launch Chromium headless when True.
        """
        self._session = PlaywrightSession(headless=headless)

    def fetch_page_html(
        self, url: str, timeout: int = 60
    ) -> Tuple[int, str, Optional[str], bool]:
        """
        Fetch page HTML via Playwright (same return shape as ``fetch_page_body``).

        Reuses the collector's Chromium session when HTTP/curl fetch fails.
        """
        if not self._ensure_browser():
            return -1, "", None, False
        page = self._session.new_page()
        if page is None:
            return -1, "", None, False
        try:
            page.set_default_timeout(timeout * 1000)
            return _fetch_html_with_playwright_page(page, url, timeout)
        finally:
            with suppress(Exception):
                page.close()

    def download_file(self, url: str, destination_path: Path) -> Tuple[int, bool]:
        """
        Download a file via Playwright (uses the browser TLS stack).

        Falls back when ``requests``/curl cannot verify fs.usda.gov certificates.
        """
        if not self._restart_browser():
            return 0, False
        page = self._session.new_page()
        if page is None:
            return 0, False
        try:
            page.set_default_timeout(_FILE_DOWNLOAD_TIMEOUT_MS)
            with page.expect_download(timeout=_FILE_DOWNLOAD_TIMEOUT_MS) as download_info:
                try:
                    page.goto(url, wait_until="commit", timeout=_FILE_DOWNLOAD_TIMEOUT_MS)
                except Exception as exc:
                    # Direct file URLs trigger a download instead of a document load.
                    if "Download is starting" not in str(exc):
                        raise
            download = download_info.value
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(destination_path))
            if destination_path.is_file():
                size = destination_path.stat().st_size
                return size, size > 0
            return 0, False
        except Exception as exc:
            Logger.error("Playwright download failed: %s - %s", url, exc)
            return 0, False
        finally:
            with suppress(Exception):
                page.close()

    def fetch_content_length(self, url: str) -> int | None:
        """
        Return Content-Length for a URL via Playwright when the server reports it.

        Args:
            url: File URL to probe.

        Returns:
            Size in bytes, or None when unavailable.
        """
        if not self._ensure_browser():
            return None
        page = self._session.new_page()
        if page is None:
            return None
        try:
            response = page.request.head(url, timeout=_CONTENT_LENGTH_TIMEOUT_MS)
            if not response.ok:
                return None
            content_length = response.headers.get("content-length")
            if not content_length:
                return None
            return int(content_length)
        except (TypeError, ValueError, OSError) as exc:
            Logger.debug("Content-Length probe failed for %s: %s", url, exc)
            return None
        finally:
            with suppress(Exception):
                page.close()

    def url_to_pdf(self, url: str, pdf_path: Path) -> bool:
        """Navigate to ``url`` and write a PDF to ``pdf_path``."""
        if not self._ensure_browser():
            return False
        page = self._session.new_page()
        if page is None:
            return False
        try:
            page.set_default_timeout(_PRINT_TIMEOUT_MS)
            page.goto(url, wait_until=_NAVIGATION_WAIT, timeout=_NAVIGATION_TIMEOUT_MS)
            page.wait_for_timeout(_SETTLE_MS)
            with suppress(Exception):
                page.wait_for_load_state("load", timeout=_LOAD_TIMEOUT_MS)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            return pdf_path.is_file() and pdf_path.stat().st_size > 0
        except Exception as exc:
            Logger.error("Failed to render PDF from %s: %s", url, exc)
            return False
        finally:
            with suppress(Exception):
                page.close()

    def html_file_to_pdf(self, html_path: Path, pdf_path: Path) -> bool:
        """Open a local HTML file in Chromium and write a PDF."""
        if not self._ensure_browser():
            return False
        page = self._session.new_page()
        if page is None:
            return False
        try:
            page.set_default_timeout(_PRINT_TIMEOUT_MS)
            page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=_LOAD_TIMEOUT_MS)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            return pdf_path.is_file() and pdf_path.stat().st_size > 0
        except Exception as exc:
            Logger.error("Failed to convert HTML to PDF (%s): %s", html_path, exc)
            return False
        finally:
            with suppress(Exception):
                page.close()

    def close(self) -> None:
        """Release Playwright resources."""
        self._session.close()

    def _restart_browser(self) -> bool:
        """Close and relaunch Chromium (fresh session before each file download)."""
        self.close()
        return self._ensure_browser()

    def _ensure_browser(self) -> bool:
        """Start Chromium without a default page when not already running."""
        if self._session.browser:
            return True
        return self._session.start(create_page=False)
