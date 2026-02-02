"""
Shared browser session for DataLumos (upload and publisher).

Provides ensure_browser(), ensure_authenticated(), and close() using Args for config.
"""

from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from utils.Args import Args
from utils.Logger import Logger


class DataLumosBrowserSession:
    """
    Shared Playwright browser session for DataLumos workflows.

    Reads Args.upload_headless, Args.upload_timeout, Args.datalumos_username,
    Args.datalumos_password. Call ensure_browser() then ensure_authenticated()
    before using the page; call close() when done.
    """

    def __init__(self) -> None:
        """Initialize session. Browser is created on first ensure_browser()."""
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._authenticated = False

    def ensure_browser(self) -> Page:
        """Ensure browser is initialized and return the page."""
        if self._page is not None:
            return self._page

        Logger.debug("Initializing Playwright browser")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=Args.upload_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        self._context.set_default_timeout(Args.upload_timeout)
        self._page = self._context.new_page()
        return self._page

    def ensure_authenticated(self) -> None:
        """Ensure user is authenticated to DataLumos. Reads Args for credentials."""
        if self._authenticated:
            return

        from upload.DataLumosAuthenticator import DataLumosAuthenticator

        page = self.ensure_browser()
        authenticator = DataLumosAuthenticator(page, timeout=Args.upload_timeout)

        if not Args.datalumos_username or not Args.datalumos_password:
            raise RuntimeError(
                "DataLumos credentials not configured. "
                "Set datalumos_username and datalumos_password in config."
            )

        authenticator.authenticate(Args.datalumos_username, Args.datalumos_password)
        self._authenticated = True

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

        self._authenticated = False
        Logger.debug("Browser resources cleaned up")
