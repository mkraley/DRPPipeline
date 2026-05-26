"""Playwright helper to render USFS web pages as PDF."""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from playwright.sync_api import Browser, Playwright, sync_playwright

from utils.Logger import Logger

_NAVIGATION_WAIT = "commit"
_NAVIGATION_TIMEOUT_MS = 30000
_SETTLE_MS = 3000
_LOAD_TIMEOUT_MS = 35000
_PRINT_TIMEOUT_MS = 90000


class UsfsPageDownloader:
    """Render USFS catalog pages in Chromium and save as PDF."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    def url_to_pdf(self, url: str, pdf_path: Path) -> bool:
        """Navigate to ``url`` and write a PDF to ``pdf_path``."""
        if not self._ensure_browser():
            return False
        assert self._browser is not None
        page = self._browser.new_page()
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
        assert self._browser is not None
        page = self._browser.new_page()
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
        if self._browser:
            with suppress(Exception):
                self._browser.close()
            self._browser = None
        if self._playwright:
            with suppress(Exception):
                self._playwright.stop()
            self._playwright = None

    def _ensure_browser(self) -> bool:
        if self._browser:
            return True
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=self._headless)
            return True
        except Exception as exc:
            Logger.error("Failed to initialize Playwright for USFS PDF export: %s", exc)
            self.close()
            return False
