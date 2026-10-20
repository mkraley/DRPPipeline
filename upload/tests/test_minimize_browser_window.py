"""Tests for keeping the DataLumos Chromium window minimized."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.minimize_browser_window import (
    keep_browser_window_minimized,
    minimize_browser_window,
)
from utils.Args import Args
from utils.Logger import Logger


class TestMinimizeBrowserWindow(unittest.TestCase):
    """CDP minimize calls and the session hook."""

    def setUp(self) -> None:
        """Initialize Args so the session can read upload settings."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "verify_upload"]
        Args.initialize()
        Logger.initialize(log_level="ERROR", log_file=False)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_minimize_sets_window_state(self) -> None:
        """The window bounds call asks Chromium to minimize."""
        page = MagicMock()
        session = page.context.new_cdp_session.return_value
        session.send.return_value = {"windowId": 7}

        minimize_browser_window(page)

        session.send.assert_any_call(
            "Browser.setWindowBounds",
            {"windowId": 7, "bounds": {"windowState": "minimized"}},
        )
        session.detach.assert_called_once()

    def test_minimize_ignores_cdp_errors(self) -> None:
        """A CDP failure does not escape to the caller."""
        page = MagicMock()
        page.context.new_cdp_session.side_effect = RuntimeError("no window")

        minimize_browser_window(page)

    def test_navigation_minimizes_only_the_main_frame(self) -> None:
        """A child frame navigation does not ask to minimize again."""
        page = MagicMock()
        page.main_frame = MagicMock(name="main")
        child = MagicMock(name="child")
        with patch("upload.minimize_browser_window.minimize_browser_window") as mock_min:
            keep_browser_window_minimized(page)
            handler = page.on.call_args.args[1]
            self.assertEqual(mock_min.call_count, 1)
            handler(child)
            self.assertEqual(mock_min.call_count, 1)
            handler(page.main_frame)
            self.assertEqual(mock_min.call_count, 2)

    def test_headed_session_keeps_the_window_minimized(self) -> None:
        """A visible DataLumos session minimizes after the page is created."""
        Args._config["upload_headless"] = False
        session = DataLumosBrowserSession()
        page = MagicMock()
        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = page
        browser.new_context.return_value = context
        playwright = MagicMock()
        playwright.chromium.launch.return_value = browser

        with patch("upload.DataLumosBrowserSession.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = playwright
            with patch(
                "upload.DataLumosBrowserSession.keep_browser_window_minimized"
            ) as mock_keep:
                opened = session.ensure_browser()

        self.assertIs(opened, page)
        mock_keep.assert_called_once_with(page)
        launch_args = playwright.chromium.launch.call_args.kwargs["args"]
        self.assertIn("--disable-backgrounding-occluded-windows", launch_args)

    def test_headless_session_does_not_minimize(self) -> None:
        """Headless launch skips the minimize hook."""
        Args._config["upload_headless"] = True
        session = DataLumosBrowserSession()
        browser = MagicMock()
        context = MagicMock()
        context.new_page.return_value = MagicMock()
        browser.new_context.return_value = context
        playwright = MagicMock()
        playwright.chromium.launch.return_value = browser

        with patch("upload.DataLumosBrowserSession.sync_playwright") as mock_pw:
            mock_pw.return_value.start.return_value = playwright
            with patch(
                "upload.DataLumosBrowserSession.keep_browser_window_minimized"
            ) as mock_keep:
                session.ensure_browser()

        mock_keep.assert_not_called()
        launch_args = playwright.chromium.launch.call_args.kwargs["args"]
        self.assertNotIn("--disable-backgrounding-occluded-windows", launch_args)


if __name__ == "__main__":
    unittest.main()
