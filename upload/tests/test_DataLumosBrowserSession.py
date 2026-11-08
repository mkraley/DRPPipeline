"""Unit tests for DataLumosBrowserSession auth helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from upload.DataLumosBrowserSession import DataLumosBrowserSession, sign_in_required
from upload.terminal_deposit_store import TerminalDepositStore
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

    def test_saved_deposit_token_is_cleared_when_the_browser_closes(self) -> None:
        """A closed browser cannot reuse the previous bearer token."""
        session = DataLumosBrowserSession()
        session.keep_deposit_token("jwt-from-first-project")
        self.assertEqual(session.deposit_token, "jwt-from-first-project")
        session.close()
        self.assertEqual(session.deposit_token, "")

    def test_reauthenticate_clears_flag_and_logs_in(self) -> None:
        """reauthenticate forces a fresh login even when already authenticated."""
        session = DataLumosBrowserSession()
        session._authenticated = True
        session.keep_deposit_token("jwt-saved")
        session._page = MagicMock()

        def _ensure(**_kwargs: object) -> None:
            self.assertFalse(session._authenticated)
            session._authenticated = True

        with patch.object(session, "ensure_authenticated", side_effect=_ensure) as mock_ensure:
            session.reauthenticate()

        mock_ensure.assert_called_once_with(reporter=None)
        self.assertTrue(session._authenticated)
        self.assertEqual(session.deposit_token, "")

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
        """A finished sign-in does not open the form again on the next project."""
        session = DataLumosBrowserSession()
        session._authenticated = True
        session._page = MagicMock()
        session._page.url = "https://www.datalumos.org/datalumos/workspace"
        with patch("upload.DataLumosAuthenticator.DataLumosAuthenticator") as auth_cls:
            session.ensure_authenticated()
        auth_cls.assert_not_called()

    def test_login_page_signs_in_again(self) -> None:
        """A browser sent to Keycloak signs in and drops the saved deposit token."""
        session = self._session_with_credentials()
        session._authenticated = True
        session.keep_deposit_token("jwt-saved")
        session._page.url = "https://login.icpsr.umich.edu/realms/icpsr"
        with patch("upload.DataLumosAuthenticator.DataLumosAuthenticator") as auth_cls:
            session.ensure_authenticated()
        auth_cls.return_value.authenticate.assert_called_once()
        self.assertEqual(session.deposit_token, "")
        self.assertTrue(session._authenticated)

    def test_sign_in_required_matches_a_rejected_deposit_call(self) -> None:
        """A 401 and a login-page redirect both ask for a new sign-in."""
        self.assertTrue(sign_in_required(RuntimeError("Deposit POST /publish failed (401)")))
        self.assertTrue(
            sign_in_required(RuntimeError("DataLumos sent the browser to the login page"))
        )
        self.assertFalse(sign_in_required(RuntimeError("view was not available")))

    def test_restored_token_skips_sign_in(self) -> None:
        """A token saved by the previous command in this terminal is reused."""
        store = self._store()
        store.save("jwt-saved", {"cookies": [{"name": "sid"}], "origins": []})
        session = DataLumosBrowserSession(store)
        session._page = MagicMock()
        session._page.url = "https://www.datalumos.org/datalumos/workspace"
        self.assertEqual(session.deposit_token, "jwt-saved")
        with patch("upload.DataLumosAuthenticator.DataLumosAuthenticator") as auth_cls:
            session.ensure_authenticated()
        auth_cls.assert_not_called()

    def test_close_leaves_the_token_for_the_next_command(self) -> None:
        """Closing the browser keeps the token and cookies for this terminal."""
        store = self._store()
        session = DataLumosBrowserSession(store)
        session.keep_deposit_token("jwt-1")
        session._context = MagicMock()
        session._context.storage_state.return_value = {
            "cookies": [{"name": "sid"}],
            "origins": [],
        }
        session.close()
        self.assertEqual(session.deposit_token, "")
        token, state = store.load()
        self.assertEqual(token, "jwt-1")
        self.assertEqual(state["cookies"][0]["name"], "sid")

    def test_restored_cookies_are_loaded_into_the_new_browser(self) -> None:
        """The next command's browser starts with the saved cookie jar."""
        store = self._store()
        cookies = {"cookies": [{"name": "sid"}], "origins": []}
        store.save("jwt-1", cookies)
        session, _page, playwright = self._browser_session(store)
        with patch("upload.DataLumosBrowserSession.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = playwright
            with patch("upload.DataLumosBrowserSession.keep_browser_window_minimized"):
                session.ensure_browser()
        state = playwright.chromium.launch.return_value.new_context.call_args.kwargs
        self.assertEqual(state["storage_state"], cookies)

    def _store(self) -> TerminalDepositStore:
        """Return a store in a private folder for one pretend terminal."""
        folder = Path(tempfile.mkdtemp())
        return TerminalDepositStore(folder, terminal_id=42)

    def test_failed_sign_in_retries_the_same_project(self) -> None:
        """One failed sign-in waits and tries again before the project continues."""
        session = self._session_with_credentials()
        auth = MagicMock()
        auth.authenticate.side_effect = [
            RuntimeError("Could not find 'Sign in with Email' button"),
            None,
        ]
        with patch(
            "upload.DataLumosAuthenticator.DataLumosAuthenticator", return_value=auth
        ), patch("upload.DataLumosBrowserSession.time.sleep") as sleep, patch(
            "upload.DataLumosBrowserSession.random.randint", return_value=15
        ):
            session.ensure_authenticated()
        self.assertEqual(auth.authenticate.call_count, 2)
        sleep.assert_called_once_with(15)
        self.assertTrue(session._authenticated)

    def test_sign_in_fails_the_project_after_three_attempts(self) -> None:
        """Three failed sign-ins stop this project and do not mark it logged in."""
        session = self._session_with_credentials()
        auth = MagicMock()
        auth.authenticate.side_effect = RuntimeError(
            "Could not find 'Sign in with Email' button"
        )
        with patch(
            "upload.DataLumosAuthenticator.DataLumosAuthenticator", return_value=auth
        ), patch("upload.DataLumosBrowserSession.time.sleep") as sleep, patch(
            "upload.DataLumosBrowserSession.random.randint", return_value=20
        ):
            with self.assertRaises(RuntimeError):
                session.ensure_authenticated()
        self.assertEqual(auth.authenticate.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertFalse(session._authenticated)

    def _session_with_credentials(self) -> DataLumosBrowserSession:
        """Return a session whose page is open and whose login is configured."""
        session = DataLumosBrowserSession()
        session._page = MagicMock()
        Args._config["datalumos_username"] = "user@example.com"
        Args._config["datalumos_password"] = "secret"
        return session

    def _browser_session(self, store: TerminalDepositStore | None = None) -> tuple:
        """Return a session whose Playwright objects are mocks."""
        page = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context
        playwright = MagicMock()
        playwright.chromium.launch.return_value = browser
        return DataLumosBrowserSession(store), page, playwright


if __name__ == "__main__":
    unittest.main()
