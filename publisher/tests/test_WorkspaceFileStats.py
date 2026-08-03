"""Unit tests for publisher.WorkspaceFileStats."""

import unittest
from unittest.mock import MagicMock, patch

from publisher.WorkspaceFileStats import workspace_file_stats_from_page


class TestWorkspaceFileStats(unittest.TestCase):
    """Tests for workspace file table scraping."""

    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_from_page_parses_table(
        self, mock_set_records: MagicMock
    ) -> None:
        """Workspace scraper reads name/size from table.table-hover columns."""
        page = MagicMock()
        page.evaluate.return_value = {
            "files": [
                {"name": "a.pdf", "size": "1.0 KB"},
                {"name": "b.zip", "size": "1.0 KB"},
            ]
        }
        stats = workspace_file_stats_from_page(page)
        mock_set_records.assert_called_once_with(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.total_bytes, 2048)
        self.assertEqual(stats.file_names, ("a.pdf", "b.zip"))

    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_from_page_no_rows(
        self, mock_set_records: MagicMock
    ) -> None:
        """Empty workspace table surfaces no_files_found."""
        page = MagicMock()
        page.evaluate.return_value = {"error": "no_files_found"}
        stats = workspace_file_stats_from_page(page)
        mock_set_records.assert_called_once_with(page)
        self.assertEqual(stats.error, "no_files_found")
        self.assertEqual(stats.file_count, 0)

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
                ]
            },
        ]
        stats = workspace_file_stats_from_page(page)
        mock_set_records.assert_called_once_with(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 1)
        self.assertEqual(page.evaluate.call_count, 2)
        page.wait_for_load_state.assert_called_once_with(
            "domcontentloaded", timeout=120000
        )


if __name__ == "__main__":
    unittest.main()
