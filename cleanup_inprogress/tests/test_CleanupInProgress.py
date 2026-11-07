"""
Unit tests for CleanupInProgress (clean_inprogress module).
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from cleanup_inprogress.CleanupInProgress import (
    CleanupInProgress,
    WORKSPACE_URL,
    _PROJECT_LIST_TIMEOUT_MS,
    resolve_keep_workspace_ids,
)


class TestCleanupInProgress(unittest.TestCase):
    """Test cases for CleanupInProgress module."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "clean_inprogress"]
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
        """Workspace URL and list timeout are set for large Hide-inactive lists."""
        self.assertIn("datalumos/workspace", WORKSPACE_URL)
        self.assertGreaterEqual(_PROJECT_LIST_TIMEOUT_MS, 300000)

    @patch("upload.DataLumosAuthenticator.wait_for_human_verification", MagicMock())
    def test_run_calls_session_and_click_hide_inactive(self) -> None:
        """Hide inactive runs before waiting for the visible project list."""
        mock_page = MagicMock()
        self.cleanup._session.ensure_browser = MagicMock(return_value=mock_page)
        self.cleanup._session.ensure_authenticated = MagicMock(return_value=None)
        self.cleanup._session.close = MagicMock(return_value=None)
        order: list[str] = []

        def _hide(_page: MagicMock) -> None:
            order.append("hide")

        def _wait(_page: MagicMock) -> None:
            order.append("wait")

        self.cleanup._click_hide_inactive = MagicMock(side_effect=_hide)
        self.cleanup._wait_for_project_list = MagicMock(side_effect=_wait)
        self.cleanup._snapshot_project_ids = MagicMock(return_value=[])
        self.cleanup._delete_via_api = MagicMock()

        self.cleanup.run(-1)

        self.cleanup._session.ensure_browser.assert_called_once()
        self.cleanup._session.ensure_authenticated.assert_called_once()
        mock_page.goto.assert_called_once_with(WORKSPACE_URL, wait_until="domcontentloaded")
        self.assertEqual(order, ["hide", "wait"])
        self.cleanup._snapshot_project_ids.assert_called_once_with(mock_page)
        self.cleanup._delete_via_api.assert_called_once_with(mock_page, [])
        self.cleanup._session.close.assert_called_once()

    @patch("upload.DataLumosAuthenticator.wait_for_human_verification", MagicMock())
    def test_run_returns_cleanly_when_project_list_times_out(self) -> None:
        """A hidden/empty project list logs an error instead of crashing."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        mock_page = MagicMock()
        self.cleanup._session.ensure_browser = MagicMock(return_value=mock_page)
        self.cleanup._session.ensure_authenticated = MagicMock(return_value=None)
        self.cleanup._session.close = MagicMock(return_value=None)
        self.cleanup._click_hide_inactive = MagicMock(return_value=None)
        self.cleanup._wait_for_project_list = MagicMock(
            side_effect=PlaywrightTimeoutError("hidden list")
        )
        self.cleanup._snapshot_project_ids = MagicMock()
        self.cleanup._delete_via_api = MagicMock()

        self.cleanup.run(-1)

        self.cleanup._snapshot_project_ids.assert_not_called()
        self.cleanup._delete_via_api.assert_not_called()
        self.cleanup._session.close.assert_called_once()

    @patch("upload.DataLumosAuthenticator.wait_for_human_verification", MagicMock())
    def test_run_aborts_when_published_visible_after_hide_inactive(self) -> None:
        """(Published) after Hide inactive is a hard error; no API deletes."""
        mock_page = MagicMock()
        self.cleanup._session.ensure_browser = MagicMock(return_value=mock_page)
        self.cleanup._session.ensure_authenticated = MagicMock(return_value=None)
        self.cleanup._session.close = MagicMock(return_value=None)
        self.cleanup._click_hide_inactive = MagicMock(return_value=None)
        self.cleanup._wait_for_project_list = MagicMock(return_value=None)
        self.cleanup._snapshot_list_html = MagicMock(
            return_value='<li><a>datalumos-1 (Published)</a></li>'
        )
        self.cleanup._delete_via_api = MagicMock()

        self.cleanup.run(-1)

        self.cleanup._delete_via_api.assert_not_called()
        self.cleanup._session.close.assert_called_once()

    @patch("cleanup_inprogress.CleanupInProgress.resolve_keep_workspace_ids")
    @patch("upload.DataLumosAuthenticator.wait_for_human_verification", MagicMock())
    def test_run_skips_protected_workspace_ids(
        self, mock_resolve: MagicMock
    ) -> None:
        """Deposits listed via --keep-ids are not passed to the API delete loop."""
        Args._config["keep_ids"] = [1346]
        mock_resolve.return_value = {"261760"}
        mock_page = MagicMock()
        self.cleanup._session.ensure_browser = MagicMock(return_value=mock_page)
        self.cleanup._session.ensure_authenticated = MagicMock(return_value=None)
        self.cleanup._session.close = MagicMock(return_value=None)
        self.cleanup._click_hide_inactive = MagicMock(return_value=None)
        self.cleanup._wait_for_project_list = MagicMock(return_value=None)
        self.cleanup._snapshot_project_ids = MagicMock(
            return_value=["261760", "999001"]
        )
        self.cleanup._delete_via_api = MagicMock()

        self.cleanup.run(-1)

        mock_resolve.assert_called_once_with([1346])
        self.cleanup._delete_via_api.assert_called_once_with(mock_page, ["999001"])

    @patch("cleanup_inprogress.CleanupInProgress.DataLumosDepositClient")
    def test_delete_via_api_calls_delete_path_without_navigation(
        self, mock_client_cls: MagicMock
    ) -> None:
        """API deletes use delete_path and never open project pages."""
        page = MagicMock()
        client = MagicMock()
        client.token = "jwt"
        mock_client_cls.return_value = client
        self.cleanup._session.keep_deposit_token = MagicMock()

        self.cleanup._delete_via_api(page, ["100", "200"])

        mock_client_cls.assert_called_once()
        client.ensure_deposit_page.assert_called_once()
        self.assertEqual(
            [call.args[0] for call in client.delete_path.call_args_list],
            ["/datalumos/100", "/datalumos/200"],
        )
        page.goto.assert_not_called()

    @patch("cleanup_inprogress.CleanupInProgress.DataLumosDepositClient")
    def test_delete_one_failure_continues(
        self, mock_client_cls: MagicMock
    ) -> None:
        """A rejected delete is logged and the next id is still attempted."""
        page = MagicMock()
        client = MagicMock()
        client.token = ""
        client.delete_path.side_effect = [RuntimeError("rejected"), None]
        mock_client_cls.return_value = client

        self.cleanup._delete_via_api(page, ["100", "200"])

        self.assertEqual(client.delete_path.call_count, 2)

    @patch("cleanup_inprogress.CleanupInProgress.Storage")
    def test_resolve_keep_workspace_ids_maps_datalumos_id(
        self, mock_storage: MagicMock
    ) -> None:
        """resolve_keep_workspace_ids looks up datalumos_id for each DRPID."""
        mock_storage.get.side_effect = lambda drpid: {
            1346: {"datalumos_id": "261760"},
            99: {"datalumos_id": None},
            100: None,
        }.get(drpid)

        result = resolve_keep_workspace_ids([1346, 99, 100])
        self.assertEqual(result, {"261760"})
        self.assertEqual(mock_storage.get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
