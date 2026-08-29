"""
Shared Playwright browser session for collectors.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Optional

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from utils.Logger import Logger


class PlaywrightSession:
    """
    Manage a Chromium Playwright session for collector modules.

    Supports a default page (Socrata/CMS/catalog) or browser-only mode (USFS).
    """

    def __init__(self, headless: bool = True, *, slow_mo: int = 0) -> None:
        """
        Initialize session settings.

        Args:
            headless: Launch Chromium headless when True.
            slow_mo: Milliseconds to slow Playwright operations (debug UI).
        """
        self._headless = headless
        self._slow_mo = slow_mo
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    @property
    def playwright(self) -> Playwright | None:
        """Underlying Playwright driver, if started."""
        return self._playwright

    @property
    def browser(self) -> Browser | None:
        """Launched browser, if started."""
        return self._browser

    @property
    def page(self) -> Page | None:
        """Default page, when ``start(create_page=True)`` was used."""
        return self._page

    def start(self, *, create_page: bool = True) -> bool:
        """
        Launch Chromium.

        Args:
            create_page: When True, create a default page on ``self.page``.

        Returns:
            True when launch succeeded.
        """
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self._headless,
                slow_mo=self._slow_mo,
            )
            if create_page:
                self._page = self._browser.new_page()
            return True
        except Exception as exc:
            Logger.error("Failed to initialize Playwright browser: %s", exc)
            self.close()
            return False

    def close(self) -> None:
        """Release browser and Playwright resources."""
        if self._browser:
            with suppress(Exception):
                self._browser.close()
            self._browser = None
        if self._playwright:
            with suppress(Exception):
                self._playwright.stop()
            self._playwright = None
        self._page = None

    def goto(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout: int = 120_000,
    ) -> bool:
        """
        Navigate the default page to ``url``.

        Args:
            url: Target URL.
            wait_until: Playwright wait_until argument.
            timeout: Navigation timeout in milliseconds.

        Returns:
            True when navigation succeeded.
        """
        if self._page is None:
            return False
        try:
            self._page.goto(url, wait_until=wait_until, timeout=timeout)
            return True
        except Exception as exc:
            Logger.error("Failed to load page %s: %s", url, exc)
            return False

    def new_page(self) -> Page | None:
        """
        Open a new browser tab.

        Returns:
            New page, or None when the browser is not started.
        """
        if self._browser is None:
            return None
        return self._browser.new_page()
