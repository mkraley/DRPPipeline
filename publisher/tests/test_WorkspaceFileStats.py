"""Unit tests for publisher.WorkspaceFileStats."""

import unittest
from unittest.mock import MagicMock, patch

from publisher.WorkspaceFileStats import workspace_file_stats_from_page
from utils.Logger import Logger


class TestWorkspaceFileStats(unittest.TestCase):
    """Tests for workspace file table scraping."""

    @classmethod
    def setUpClass(cls) -> None:
        Logger.initialize(log_level="WARNING")

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_from_page_parses_table(
        self, mock_set_records: MagicMock, mock_wait: MagicMock
    ) -> None:
        """Workspace scraper reads name/size from table.table-hover columns."""
        page = MagicMock()
        page.evaluate.return_value = {
            "files": [
                {"name": "a.pdf", "size": "1.0 KB"},
                {"name": "b.zip", "size": "1.0 KB"},
            ],
            "totalRecords": 2,
        }
        stats = workspace_file_stats_from_page(page)
        mock_set_records.assert_called_once_with(page, 100)
        mock_wait.assert_called()
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.total_bytes, 2048)
        self.assertEqual(stats.file_names, ("a.pdf", "b.zip"))

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_from_page_no_rows(
        self, mock_set_records: MagicMock, mock_wait: MagicMock
    ) -> None:
        """Empty workspace table surfaces no_files_found."""
        page = MagicMock()
        page.evaluate.return_value = {"error": "no_files_found"}
        stats = workspace_file_stats_from_page(page)
        mock_set_records.assert_called_once_with(page, 100)
        self.assertEqual(stats.error, "no_files_found")
        self.assertEqual(stats.file_count, 0)

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_retries_when_capped_at_default_page(
        self, mock_set_records: MagicMock, mock_wait: MagicMock
    ) -> None:
        """When Total is 11 but only 10 rows show, retry until all rows appear."""
        page = MagicMock()
        ten_files = [{"name": f"f{i}.csv", "size": "1.0 KB"} for i in range(10)]
        eleven_files = ten_files + [{"name": "f10.csv", "size": "1.0 KB"}]
        page.evaluate.side_effect = [
            {"files": ten_files, "totalRecords": 11},
            {"files": eleven_files, "totalRecords": 11},
        ]
        stats = workspace_file_stats_from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 11)
        self.assertEqual(mock_set_records.call_count, 2)

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_incomplete_after_retries(
        self, mock_set_records: MagicMock, mock_wait: MagicMock
    ) -> None:
        """Persistent undercount returns incomplete_page instead of a silent 10."""
        page = MagicMock()
        ten_files = [{"name": f"f{i}.csv", "size": "1.0 KB"} for i in range(10)]
        page.evaluate.return_value = {"files": ten_files, "totalRecords": 11}
        stats = workspace_file_stats_from_page(page)
        self.assertIsNotNone(stats.error)
        assert stats.error is not None
        self.assertIn("incomplete_page", stats.error)
        self.assertEqual(stats.file_count, 10)
        self.assertEqual(mock_set_records.call_count, 3)

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_from_page_retries_after_navigation_race(
        self, mock_set_records: MagicMock, mock_wait_table: MagicMock
    ) -> None:
        """Scraper retries evaluate when pager navigation destroys context."""
        page = MagicMock()
        page.evaluate.side_effect = [
            Exception(
                "Page.evaluate: Execution context was destroyed, "
                "most likely because of a navigation"
            ),
            {
                "files": [
                    {"name": "a.csv", "size": "1.0 KB"},
                ],
                "totalRecords": 1,
            },
        ]
        stats = workspace_file_stats_from_page(page)
        mock_set_records.assert_called_once_with(page, 100)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 1)
        self.assertEqual(page.evaluate.call_count, 2)
        page.wait_for_load_state.assert_called_once_with(
            "domcontentloaded", timeout=120000
        )


if __name__ == "__main__":
    unittest.main()
