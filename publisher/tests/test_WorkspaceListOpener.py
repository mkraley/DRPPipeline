"""Unit tests for opening a DataLumos project from the workspace list."""

import unittest
from unittest.mock import MagicMock

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from publisher.WorkspaceListOpener import WorkspaceListOpener
from utils.Logger import Logger


class TestWorkspaceListOpener(unittest.TestCase):
    """The workspace list is used only when it is actually on screen."""

    def setUp(self) -> None:
        """Initialize logging so opener messages have a logger."""
        Logger.initialize(log_level="WARNING")
        self.opener = WorkspaceListOpener()

    def test_skips_click_when_the_list_is_not_showing(self) -> None:
        """A page without the workspace search box is left alone."""
        page = MagicMock()
        page.locator.return_value.count.return_value = 0
        self.assertFalse(self.opener.open_if_list_showing(page, "260027"))
        page.locator.return_value.first.fill.assert_not_called()

    def test_searches_and_clicks_the_project_link(self) -> None:
        """A visible list is searched, then the matching project link is clicked."""
        page = self._page_with_list()
        self.assertTrue(self.opener.open_if_list_showing(page, "260027"))
        page.locator.return_value.first.fill.assert_called_once_with("260027")
        page.locator.return_value.first.click.assert_called_once()

    def test_reports_when_the_project_link_is_missing(self) -> None:
        """A list that never shows the project link does not click."""
        page = self._page_with_list()
        page.locator.return_value.first.wait_for.side_effect = PlaywrightTimeoutError(
            "missing"
        )
        self.assertFalse(self.opener.open_if_list_showing(page, "260027"))
        page.locator.return_value.first.click.assert_not_called()

    def _page_with_list(self) -> MagicMock:
        """Return a page whose workspace search box is visible."""
        page = MagicMock()
        page.url = "https://www.datalumos.org/datalumos/workspace?goToPath=/datalumos/260027#"
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.first.is_visible.return_value = True
        return page
