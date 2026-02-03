"""
Unit tests for CleanupInProgress (cleanup_inprogress module).
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from cleanup_inprogress.CleanupInProgress import (
    CleanupInProgress,
    PROJECT_URL_TEMPLATE,
    WORKSPACE_URL,
    DEPOSIT_IN_PROGRESS_TEXT,
)


class TestCleanupInProgress(unittest.TestCase):
    """Test cases for CleanupInProgress module."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "cleanup_inprogress"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.cleanup = CleanupInProgress()

    def tearDown(self) -> None:
        """Restore argv and Args after each test."""
        sys.argv = self._original_argv
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}

    def test_constants(self) -> None:
        """Test workspace URL and project URL template."""
        self.assertIn("datalumos/workspace", WORKSPACE_URL)
        url = PROJECT_URL_TEMPLATE.format(workspace_id="244401")
        self.assertIn("goToLevel=project", url)
        self.assertIn("/datalumos/244401", url)
        self.assertEqual(DEPOSIT_IN_PROGRESS_TEXT, "[Deposit In Progress]")

    def test_confirm_deposit_in_progress_true(self) -> None:
        """Test _confirm_deposit_in_progress returns True when third span has expected text."""
        page = MagicMock()
        third_span = MagicMock()
        third_span.count.return_value = 1
        third_span.first.inner_text.return_value = " [Deposit In Progress] "
        page.locator.return_value = third_span

        result = self.cleanup._confirm_deposit_in_progress(page, "123")
        self.assertTrue(result)
        page.locator.assert_called_once()
        call_arg = page.locator.call_args[0][0]
        self.assertIn("span[3]", call_arg)

    def test_confirm_deposit_in_progress_false_no_span(self) -> None:
        """Test _confirm_deposit_in_progress returns False when third span is missing."""
        page = MagicMock()
        third_span = MagicMock()
        third_span.count.return_value = 0
        page.locator.return_value = third_span

        result = self.cleanup._confirm_deposit_in_progress(page, "456")
        self.assertFalse(result)

    def test_confirm_deposit_in_progress_false_wrong_text(self) -> None:
        """Test _confirm_deposit_in_progress returns False when text is not [Deposit In Progress]."""
        page = MagicMock()
        third_span = MagicMock()
        third_span.count.return_value = 1
        third_span.first.inner_text.return_value = "Published"
        page.locator.return_value = third_span

        result = self.cleanup._confirm_deposit_in_progress(page, "789")
        self.assertFalse(result)

    def test_get_project_ids_from_list_empty(self) -> None:
        """Test _get_project_ids_from_list returns empty list when no list-group."""
        page = MagicMock()
        list_group = MagicMock()
        list_group.count.return_value = 0
        page.locator.return_value = list_group

        result = self.cleanup._get_project_ids_from_list(page)
        self.assertEqual(result, [])
        page.locator.assert_any_call("ul.list-group")

    def test_get_project_ids_from_list_extracts_ids(self) -> None:
        """Test _get_project_ids_from_list extracts workspace ID from link text (datalumos-244787)."""
        page = MagicMock()
        list_group = MagicMock()
        list_group.count.return_value = 1
        items = MagicMock()
        items.count.return_value = 1
        link = MagicMock()
        link.count.return_value = 1
        link.inner_text.return_value = "datalumos-244787"
        li = MagicMock()
        li.locator.return_value.first = link
        items.nth.return_value = li
        list_group.locator.return_value = items
        page.locator.return_value = list_group

        result = self.cleanup._get_project_ids_from_list(page)
        self.assertEqual(result, ["244787"])

    def test_get_project_ids_from_list_skips_li_without_datalumos_id_in_text(self) -> None:
        """Test _get_project_ids_from_list skips li when link text has no datalumos-<id>."""
        page = MagicMock()
        list_group = MagicMock()
        list_group.count.return_value = 1
        items = MagicMock()
        items.count.return_value = 1
        link = MagicMock()
        link.count.return_value = 1
        link.inner_text.return_value = "Other label"
        li = MagicMock()
        li.locator.return_value.first = link
        items.nth.return_value = li
        list_group.locator.return_value = items
        page.locator.return_value = list_group

        result = self.cleanup._get_project_ids_from_list(page)
        self.assertEqual(result, [])

    @patch("upload.DataLumosAuthenticator.wait_for_human_verification", MagicMock())
    def test_run_calls_session_and_click_hide_inactive(self) -> None:
        """Test run ensures browser, auth, goto workspace, click Hide inactive, then close."""
        mock_page = MagicMock()
        self.cleanup._session.ensure_browser = MagicMock(return_value=mock_page)
        self.cleanup._session.ensure_authenticated = MagicMock(return_value=None)
        self.cleanup._session.close = MagicMock(return_value=None)
        self.cleanup._click_hide_inactive = MagicMock(return_value=None)
        self.cleanup._get_project_ids_from_list = MagicMock(return_value=[])

        self.cleanup.run(-1)

        self.cleanup._session.ensure_browser.assert_called_once()
        self.cleanup._session.ensure_authenticated.assert_called_once()
        mock_page.goto.assert_called_once_with(WORKSPACE_URL, wait_until="domcontentloaded")
        self.cleanup._click_hide_inactive.assert_called_once_with(mock_page)
        self.cleanup._get_project_ids_from_list.assert_called_once_with(mock_page)
        self.cleanup._session.close.assert_called_once()
