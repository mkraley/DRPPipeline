"""
Shared browser session for DataLumos (upload and publisher).

Provides ensure_browser(), ensure_authenticated(), reauthenticate(), and close()
using Args for config.
"""

import atexit
import random
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from upload.minimize_browser_window import (
    AWAKE_WHEN_MINIMIZED_ARGS,
    keep_browser_window_minimized,
)
from utils.Args import Args
from utils.Logger import Logger

if TYPE_CHECKING:
    from upload.UploadIssueReporter import UploadIssueReporter

# A failed sign-in is retried on the same project before that project is failed.
LOGIN_MAX_ATTEMPTS = 3
LOGIN_RETRY_MIN_SECONDS = 10
LOGIN_RETRY_MAX_SECONDS = 60


class DataLumosBrowserSession:
    """
    Shared Playwright browser session for DataLumos workflows.

    Reads Args.upload_headless, Args.upload_timeout, Args.upload_viewport_width,
    Args.upload_viewport_height, Args.upload_record_video_dir, Args.datalumos_username,
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
        self._deposit_token = ""
        self._exit_registered = False

    @property
    def deposit_token(self) -> str:
        """Bearer token saved after the first workspace open in this session."""
        return self._deposit_token

    def keep_deposit_token(self, token: str) -> None:
        """Remember a deposit bearer token for the rest of this browser session.

        Later projects send this token themselves. A rejected token is stored
        as empty so the next project can open the workspace once.
        """
        self._deposit_token = token or ""

    def ensure_browser(self) -> Page:
        """Ensure browser is initialized and return the page."""
        if self._page is not None and _page_still_open(self._page):
            return self._page
        if self._page is not None or self._browser is not None:
            self.close()
        self._start_browser()
        if not self._exit_registered:
            atexit.register(self.close)
            self._exit_registered = True
        return self._page

    def _start_browser(self) -> None:
        """Launch Chromium and open one page."""
        Logger.debug("Initializing Playwright browser")
        self._playwright = sync_playwright().start()
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ]
        if not Args.upload_headless:
            launch_args.extend(AWAKE_WHEN_MINIMIZED_ARGS)
        self._browser = self._playwright.chromium.launch(
            headless=Args.upload_headless,
            args=launch_args,
        )
        viewport = {
            "width": int(Args.upload_viewport_width),
            "height": int(Args.upload_viewport_height),
        }
        ctx_kwargs: dict[str, Any] = {
            "viewport": viewport,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "locale": "en-US",
            "timezone_id": "America/New_York",
        }
        record_dir = Args.upload_record_video_dir
        if record_dir:
            out_dir = Path(str(record_dir)).expanduser()
            ctx_kwargs["record_video_dir"] = str(out_dir)
            ctx_kwargs["record_video_size"] = viewport
            try:
                resolved = str(out_dir.resolve())
            except OSError:
                resolved = str(out_dir)
            Logger.info(
                "Playwright video recording enabled; WebM files are written under %s when the session closes.",
                resolved,
            )
        self._context = self._browser.new_context(**ctx_kwargs)
        self._context.set_default_timeout(Args.upload_timeout)
        self._page = self._context.new_page()
        if not Args.upload_headless:
            keep_browser_window_minimized(self._page)

    def ensure_authenticated(self, reporter: Optional["UploadIssueReporter"] = None) -> None:
        """Sign in once per batch, and again when the browser is on the login page."""
        if self._authenticated and not self._on_login_page():
            return
        if self._on_login_page():
            Logger.info("DataLumos sent the browser to the login page; signing in again")
            self._drop_login()
        self._require_credentials()
        self._sign_in_with_retries(reporter)

    def _require_credentials(self) -> None:
        """Raise when the DataLumos username or password is missing."""
        if Args.datalumos_username and Args.datalumos_password:
            return
        raise RuntimeError(
            "DataLumos credentials not configured. "
            "Set datalumos_username and datalumos_password in config."
        )

    def _sign_in_with_retries(self, reporter: Optional["UploadIssueReporter"]) -> None:
        """Sign in, pausing and retrying this project after a transient failure."""
        last_error: Exception | None = None
        for attempt in range(1, LOGIN_MAX_ATTEMPTS + 1):
            try:
                self._authenticate_once(reporter)
            except RuntimeError as exc:
                last_error = exc
                self._pause_before_login_retry(attempt, exc)
                continue
            self._note_login_success(attempt)
            return
        if last_error is not None:
            raise last_error
        raise RuntimeError("DataLumos sign-in failed")

    def _authenticate_once(self, reporter: Optional["UploadIssueReporter"]) -> None:
        """Run one sign-in against the current page."""
        from upload.DataLumosAuthenticator import DataLumosAuthenticator

        page = self.ensure_browser()
        DataLumosAuthenticator(
            page, timeout=Args.upload_timeout, reporter=reporter
        ).authenticate(Args.datalumos_username, Args.datalumos_password)

    def _pause_before_login_retry(self, attempt: int, exc: BaseException) -> None:
        """Log a failed sign-in and wait before another try on this project."""
        if attempt >= LOGIN_MAX_ATTEMPTS:
            Logger.error(
                "DataLumos sign-in failed %s times on this project: %s",
                LOGIN_MAX_ATTEMPTS,
                exc,
            )
            return
        delay = random.randint(LOGIN_RETRY_MIN_SECONDS, LOGIN_RETRY_MAX_SECONDS)
        Logger.warning(
            "DataLumos sign-in attempt %s of %s failed (%s); "
            "retrying this project in %s seconds",
            attempt,
            LOGIN_MAX_ATTEMPTS,
            exc,
            delay,
        )
        time.sleep(delay)

    def _note_login_success(self, attempt: int) -> None:
        """Record a successful sign-in and say when it took more than one try."""
        self._authenticated = True
        if attempt == 1:
            return
        Logger.info(
            "DataLumos sign-in succeeded on attempt %s of %s",
            attempt,
            LOGIN_MAX_ATTEMPTS,
        )

    def reauthenticate(self, reporter: Optional["UploadIssueReporter"] = None) -> None:
        """
        Force a fresh DataLumos login, even when already marked authenticated.

        A rejected deposit call uses this. The saved bearer token is dropped
        so the next deposit call reads a new one.
        """
        Logger.info("Re-authenticating with DataLumos")
        self._drop_login()
        self.ensure_authenticated(reporter=reporter)

    def _on_login_page(self) -> bool:
        """Return True when the open page is the DataLumos or Keycloak sign-in page."""
        from upload.DataLumosAuthenticator import page_needs_login

        return page_needs_login(self._page)

    def _drop_login(self) -> None:
        """Forget the sign-in and the bearer token saved for this browser."""
        self._authenticated = False
        self._deposit_token = ""

    def close(self) -> None:
        """
        Close the browser and clean up resources.

        During Ctrl-C (KeyboardInterrupt active), abandons Playwright handles
        without awaiting in-flight page ops — graceful ``page.close()`` otherwise
        leaves pending asyncio tasks that spam the console on exit.
        """
        if sys.exc_info()[0] is KeyboardInterrupt:
            self._abandon()
            return

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

        self._drop_login()
        Logger.debug("Browser resources cleaned up")

    def _abandon(self) -> None:
        """
        Drop Playwright refs without awaiting interrupted page operations.

        Avoids ``page.close()`` / ``playwright.stop()`` during Ctrl-C — those
        leave pending asyncio tasks that log ERROR on interpreter shutdown.
        Process exit (``os._exit`` from the Ctrl-C handler) reaps the browser.
        """
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._drop_login()
        Logger.debug("Browser resources abandoned after interrupt")


def _page_still_open(page: Page) -> bool:
    """Return True when the page is still usable. Non-boolean results count as open."""
    checker = getattr(page, "is_closed", None)
    if not callable(checker):
        return True
    try:
        closed = checker()
    except Exception:
        return False
    if not isinstance(closed, bool):
        return True
    return not closed


def sign_in_required(exc: BaseException) -> bool:
    """Return True when a deposit rejection or a login page needs a new sign-in."""
    text = str(exc)
    return "(401)" in text or "sent the browser to the login page" in text
