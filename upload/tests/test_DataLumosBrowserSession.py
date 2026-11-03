"""Unit tests for DataLumosBrowserSession auth helpers."""

from __future__ import annotations

import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from upload.DataLumosBrowserSession import LOGIN_MAX_AGE_SECONDS, DataLumosBrowserSession
from utils.Args import Args
from utils.Logger import Logger


class TestDataLumosBrowserSession(unittest.TestCase):
    """Tests for session authentication helpers."""

    def setUp(self) -> None:
        """Initialize Args and logger for session methods."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "verify_upload"]
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_reauthenticate_clears_flag_and_logs_in(self) -> None:
        """reauthenticate forces a fresh login even when already authenticated."""
        session = DataLumosBrowserSession()
        session._authenticated = True
        session._page = MagicMock()

        def _ensure(**_kwargs: object) -> None:
            self.assertFalse(session._authenticated)
            session._authenticated = True

        with patch.object(session, "ensure_authenticated", side_effect=_ensure) as mock_ensure:
            session.reauthenticate()

        mock_ensure.assert_called_once_with(reporter=None)
        self.assertTrue(session._authenticated)

    def test_ensure_authenticated_skips_when_already_authed(self) -> None:
        """ensure_authenticated is a no-op when the session is already marked authenticated."""
        session = DataLumosBrowserSession()
        session._authenticated = True

        with patch(
            "upload.DataLumosAuthenticator.DataLumosAuthenticator"
        ) as mock_auth_cls:
            session.ensure_authenticated()

        mock_auth_cls.assert_not_called()

    def test_close_abandons_without_page_close_on_keyboard_interrupt(self) -> None:
        """Ctrl-C path must not call page.close() (pending asyncio task spam)."""
        session = DataLumosBrowserSession()
        mock_page = MagicMock()
        mock_browser = MagicMock()
        session._page = mock_page
        session._context = MagicMock()
        session._browser = mock_browser
        session._playwright = MagicMock()
        session._authenticated = True

        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            session.close()

        mock_page.close.assert_not_called()
        mock_browser.close.assert_not_called()
        self.assertIsNone(session._page)
        self.assertIsNone(session._browser)
        self.assertIsNone(session._playwright)
        self.assertFalse(session._authenticated)

    def test_second_ensure_browser_reuses_the_open_page(self) -> None:
        """A batch keeps the same page instead of launching a new browser."""
        session, page, playwright = self._browser_session()
        page.is_closed.return_value = False
        with patch("upload.DataLumosBrowserSession.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = playwright
            with patch("upload.DataLumosBrowserSession.keep_browser_window_minimized"):
                first = session.ensure_browser()
                second = session.ensure_browser()
        self.assertIs(first, second)
        self.assertIs(first, page)
        playwright.chromium.launch.assert_called_once()

    def test_closed_page_starts_a_new_browser(self) -> None:
        """A page closed by the site is replaced on the next project."""
        session, page, playwright = self._browser_session()
        page.is_closed.return_value = True
        with patch("upload.DataLumosBrowserSession.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = playwright
            with patch("upload.DataLumosBrowserSession.keep_browser_window_minimized"):
                session.ensure_browser()
                session.ensure_browser()
        self.assertEqual(playwright.chromium.launch.call_count, 2)

    def test_recent_login_is_reused(self) -> None:
        """A login younger than 30 minutes does not open the sign-in form again."""
        session = DataLumosBrowserSession()
        session._authenticated = True
        session._authenticated_at = time.monotonic()
        session._page = MagicMock()
        with patch("upload.DataLumosAuthenticator.DataLumosAuthenticator") as auth_cls:
            session.ensure_authenticated()
        auth_cls.assert_not_called()

    def test_login_refreshes_after_thirty_minutes(self) -> None:
        """A login that is 30 minutes old signs in again."""
        session = DataLumosBrowserSession()
        session._authenticated = True
        session._authenticated_at = time.monotonic() - (LOGIN_MAX_AGE_SECONDS + 1)
        session._page = MagicMock()
        Args._config["datalumos_username"] = "user@example.com"
        Args._config["datalumos_password"] = "secret"
        with patch("upload.DataLumosAuthenticator.DataLumosAuthenticator") as auth_cls:
            session.ensure_authenticated()
        auth_cls.return_value.authenticate.assert_called_once()
        self.assertTrue(session._authenticated)

    def _browser_session(self) -> tuple:
        """Return a session whose Playwright objects are mocks."""
        page = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context
        playwright = MagicMock()
        playwright.chromium.launch.return_value = browser
        return DataLumosBrowserSession(), page, playwright


if __name__ == "__main__":
    unittest.main()
