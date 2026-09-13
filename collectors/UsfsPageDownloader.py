"""Playwright helper to render USFS web pages as PDF."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import Any, Optional, Tuple
from urllib.parse import unquote, urlparse

from collectors.PlaywrightSession import PlaywrightSession
from utils.Logger import Logger
from utils.file_utils import sanitize_filename
from utils.url_utils import _fetch_html_with_playwright_page

_NAVIGATION_WAIT = "commit"
_NAVIGATION_TIMEOUT_MS = 30000
_SETTLE_MS = 3000
_LOAD_TIMEOUT_MS = 35000
_PRINT_TIMEOUT_MS = 90000
_FILE_DOWNLOAD_TIMEOUT_MS = 600 * 1000
_CONTENT_LENGTH_TIMEOUT_MS = 30_000
_INLINE_DOCUMENT_SUFFIXES = frozenset({".xml", ".json", ".txt", ".csv"})


def _is_inline_document_url(url: str) -> bool:
    """
    Return True when Chromium is likely to render the URL as a page.

    XML/JSON/TXT/CSV are often served with a document Content-Type, so
    ``expect_download`` never fires.
    """
    suffix = Path(unquote(urlparse(url).path)).suffix.lower()
    return suffix in _INLINE_DOCUMENT_SUFFIXES


def _unique_pdf_path(path: Path) -> Path:
    """Return ``path``, or ``stem_2.pdf`` / ``stem_3.pdf`` if it already exists."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


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
        Download a file via Playwright or Chrome Range chunks.

        ROSA P uses Chrome-impersonated Range downloads (Akamai blocks plain
        HTTP and truncates long single-stream browser transfers). XML/JSON
        and similar documents are fetched with the browser request API
        because Chromium renders them instead of firing a download event.
        """
        from utils.ChromeRangeDownload import (
            download_via_chrome_ranges,
            requires_chrome_range_download,
        )

        if requires_chrome_range_download(url):
            return download_via_chrome_ranges(url, destination_path)
        if _is_inline_document_url(url):
            return self._download_via_api_request(url, destination_path)
        return self._download_via_browser_event(url, destination_path)

    def _download_via_api_request(
        self, url: str, destination_path: Path
    ) -> Tuple[int, bool]:
        """GET the URL through Playwright's request context and write bytes."""
        if not self._restart_browser():
            return 0, False
        page = self._session.new_page()
        if page is None:
            return 0, False
        try:
            response = page.request.get(url, timeout=_FILE_DOWNLOAD_TIMEOUT_MS)
            if not response.ok:
                Logger.error(
                    "Playwright GET failed: %s - HTTP %s", url, response.status
                )
                return 0, False
            body = response.body()
            if not body:
                Logger.error("Playwright GET returned an empty body: %s", url)
                return 0, False
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            destination_path.write_bytes(body)
            return len(body), True
        except Exception as exc:
            Logger.error("Playwright GET failed: %s - %s", url, exc)
            return 0, False
        finally:
            with suppress(Exception):
                page.close()

    def _download_via_browser_event(
        self, url: str, destination_path: Path
    ) -> Tuple[int, bool]:
        """Save a browser download event triggered by navigating to ``url``."""
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
        Return Content-Length for a URL when the server reports it.

        ROSA P uses Chrome-impersonated HEAD (Playwright API requests get 403).
        """
        from utils.ChromeRangeDownload import (
            probe_content_length,
            requires_chrome_range_download,
        )

        if requires_chrome_range_download(url):
            return probe_content_length(url)

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

    def url_to_pdf(
        self,
        url: str,
        pdf_path: Path,
        *,
        open_details_selector: str | None = None,
    ) -> bool:
        """Navigate to ``url`` and write a PDF to ``pdf_path``."""
        return self._render_pdf(url, pdf_path, open_details_selector) is not None

    def url_to_titled_pdf(
        self,
        url: str,
        dest_dir: Path,
        fallback_stem: str = "page",
    ) -> Path | None:
        """
        Render ``url`` to a PDF named from the document ``<title>``.

        Args:
            url: Page to print.
            dest_dir: Folder that receives the PDF.
            fallback_stem: Filename stem when the page has no title.

        Returns:
            Path of the written PDF, or None on failure.
        """
        if not self._ensure_browser():
            return None
        page = self._session.new_page()
        if page is None:
            return None
        try:
            self._prepare_page_for_pdf(page, url)
            stem = sanitize_filename(str(page.title() or "").strip()) 
            if stem == "Untitled":
                stem = sanitize_filename(fallback_stem)
            filename = stem if stem.lower().endswith(".pdf") else f"{stem}.pdf"
            dest_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = _unique_pdf_path(dest_dir / filename)
            return self._write_page_pdf(page, pdf_path)
        except Exception as exc:
            Logger.error("Failed to render titled PDF from %s: %s", url, exc)
            return None
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

    def _render_pdf(
        self,
        url: str,
        pdf_path: Path,
        open_details_selector: str | None,
    ) -> Path | None:
        """Navigate, optionally expand a details section, and print to PDF."""
        if not self._ensure_browser():
            return None
        page = self._session.new_page()
        if page is None:
            return None
        try:
            self._prepare_page_for_pdf(page, url, open_details_selector)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            return self._write_page_pdf(page, pdf_path)
        except Exception as exc:
            Logger.error("Failed to render PDF from %s: %s", url, exc)
            return None
        finally:
            with suppress(Exception):
                page.close()

    def _prepare_page_for_pdf(
        self,
        page: Any,
        url: str,
        open_details_selector: str | None = None,
    ) -> None:
        """Load ``url`` and expand a ``<details>`` section when requested."""
        page.set_default_timeout(_PRINT_TIMEOUT_MS)
        page.goto(url, wait_until=_NAVIGATION_WAIT, timeout=_NAVIGATION_TIMEOUT_MS)
        page.wait_for_timeout(_SETTLE_MS)
        with suppress(Exception):
            page.wait_for_load_state("load", timeout=_LOAD_TIMEOUT_MS)
        if open_details_selector:
            self._open_closest_details(page, open_details_selector)

    def _open_closest_details(self, page: Any, selector: str) -> None:
        """Open the ``<details>`` ancestor of the first matching element."""
        with suppress(Exception):
            page.locator(selector).first.evaluate(
                "element => { const details = element.closest('details');"
                " if (details) details.open = true; }"
            )

    def _write_page_pdf(self, page: Any, pdf_path: Path) -> Path | None:
        """Print the current page to ``pdf_path``."""
        page.pdf(path=str(pdf_path), format="A4", print_background=True)
        if pdf_path.is_file() and pdf_path.stat().st_size > 0:
            return pdf_path
        return None

    def _restart_browser(self) -> bool:
        """Close and relaunch Chromium (fresh session before each file download)."""
        self.close()
        return self._ensure_browser()

    def _ensure_browser(self) -> bool:
        """Start Chromium without a default page when not already running."""
        if self._session.browser:
            return True
        return self._session.start(create_page=False)
