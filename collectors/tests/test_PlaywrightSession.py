"""Tests for shared PlaywrightSession helper."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from collectors.PlaywrightSession import PlaywrightSession


class TestPlaywrightSession(unittest.TestCase):
    """Tests for PlaywrightSession lifecycle."""

    @patch("collectors.PlaywrightSession.sync_playwright")
    def test_start_creates_page_by_default(self, mock_sync: MagicMock) -> None:
        """start(create_page=True) exposes a default page."""
        playwright = MagicMock()
        browser = MagicMock()
        page = MagicMock()
        mock_sync.return_value.start.return_value = playwright
        playwright.chromium.launch.return_value = browser
        browser.new_page.return_value = page

        session = PlaywrightSession(headless=True)
        self.assertTrue(session.start())
        self.assertIs(session.page, page)
        session.close()
        browser.close.assert_called_once()
        playwright.stop.assert_called_once()

    @patch("collectors.PlaywrightSession.sync_playwright")
    def test_start_browser_only(self, mock_sync: MagicMock) -> None:
        """start(create_page=False) launches browser without a default page."""
        playwright = MagicMock()
        browser = MagicMock()
        mock_sync.return_value.start.return_value = playwright
        playwright.chromium.launch.return_value = browser

        session = PlaywrightSession(headless=True)
        self.assertTrue(session.start(create_page=False))
        self.assertIsNone(session.page)
        browser.new_page.assert_not_called()
        session.close()

    @patch("collectors.PlaywrightSession.sync_playwright")
    def test_goto_returns_false_without_page(self, mock_sync: MagicMock) -> None:
        """goto fails when no default page exists."""
        session = PlaywrightSession(headless=True)
        self.assertFalse(session.goto("https://example.com"))


if __name__ == "__main__":
    unittest.main()
