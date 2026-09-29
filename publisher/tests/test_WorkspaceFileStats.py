"""Unit tests for publisher.WorkspaceFileStats."""

import unittest
from unittest.mock import MagicMock, patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from publisher.WorkspaceFileStats import (
    _open_workspace_folder,
    workspace_file_stats_from_page,
    workspace_storage_mismatches,
)
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

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_descends_into_folders(
        self, mock_set_records: MagicMock, mock_wait: MagicMock
    ) -> None:
        """Folder rows are opened so nested files are counted."""
        page = MagicMock()
        page.evaluate.side_effect = [
            {
                "files": [
                    {"name": "readme.pdf", "type": "File", "size": "1.0 KB"},
                    {"name": "Mammal_inventory", "type": "Folder", "size": ""},
                ],
                "totalRecords": 2,
            },
            {
                "files": [
                    {"name": "report.pdf", "type": "File", "size": "1.0 KB"},
                ],
                "totalRecords": 1,
            },
        ]
        stats = workspace_file_stats_from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.total_bytes, 2048)
        self.assertEqual(stats.file_names, ("readme.pdf", "report.pdf"))
        page.go_back.assert_called_once()

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    @patch("publisher.WorkspaceFileStats.set_records_per_page", return_value=True)
    def test_workspace_file_stats_folder_icon_without_type(
        self, mock_set_records: MagicMock, mock_wait: MagicMock
    ) -> None:
        """Folders identified by glyphicon-folder-open are still walked."""
        page = MagicMock()
        page.evaluate.side_effect = [
            {
                "files": [
                    {"name": "readme.pdf", "type": "", "size": "1.0 KB", "isFolder": False},
                    {
                        "name": "Mammal_inventory",
                        "type": "",
                        "size": "",
                        "isFolder": True,
                    },
                ],
                "totalRecords": 2,
            },
            {
                "files": [
                    {"name": "report.pdf", "type": "", "size": "1.0 KB", "isFolder": False},
                ],
                "totalRecords": 1,
            },
        ]
        stats = workspace_file_stats_from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.file_names, ("readme.pdf", "report.pdf"))

    @patch("publisher.WorkspaceFileStats.wait_for_workspace_file_table")
    def test_open_folder_retries_after_busy_overlay_timeout(
        self, _mock_wait: MagicMock
    ) -> None:
        """A click blocked by #busy is retried after the overlay clears."""
        page = MagicMock()
        busy = MagicMock()
        busy.count.return_value = 1
        cell = MagicMock()
        cell.click.side_effect = [
            PlaywrightTimeoutError("busy intercepts"),
            None,
        ]
        row = MagicMock()
        row.locator.return_value.nth.return_value = cell
        table = MagicMock()
        table.filter.return_value.first = row

        def locator(selector: str) -> MagicMock:
            if selector == "#busy":
                return busy
            return table

        page.locator.side_effect = locator
        _open_workspace_folder(page, "Analyzing_Population_Trends")
        self.assertEqual(cell.click.call_count, 2)
        busy.first.wait_for.assert_called()

    @patch("publisher.WorkspaceFileStats.nps_product_folder_count", return_value=1)
    def test_storage_status_counts_files_plus_product_folders(
        self, _mock_products: MagicMock
    ) -> None:
        """Panel file/folder count is num_files plus product folders."""
        page = MagicMock()
        page.evaluate.return_value = {"space": "< 0.01 GB", "fileFolder": "4"}
        errors = workspace_storage_mismatches(
            page,
            {"DRPID": 1, "num_files": 3, "file_size": "571.9 KB"},
        )
        self.assertEqual(errors, [])

    @patch("publisher.WorkspaceFileStats.nps_product_folder_count", return_value=1)
    def test_storage_status_reports_count_mismatch(
        self, _mock_products: MagicMock
    ) -> None:
        """A panel count that is not num_files plus products is a mismatch."""
        page = MagicMock()
        page.evaluate.return_value = {"space": "< 0.01 GB", "fileFolder": "3"}
        errors = workspace_storage_mismatches(
            page,
            {"DRPID": 1, "num_files": 3, "file_size": "571.9 KB"},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("files=4/3", errors[0])

    def test_storage_status_rejects_size_above_upper_bound(self) -> None:
        """A database size at or above '< 0.01 GB' does not match."""
        page = MagicMock()
        page.evaluate.return_value = {"space": "< 0.01 GB", "fileFolder": "2"}
        errors = workspace_storage_mismatches(
            page,
            {"num_files": 2, "file_size": "20 MB"},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("size=20 MB/< 0.01 GB", errors[0])

    @patch("publisher.WorkspaceFileStats.nps_product_folder_count", return_value=0)
    def test_rounded_gigabyte_label_matches_within_display_step(
        self, _mock_products: MagicMock
    ) -> None:
        """14.5 MB displays as 0.01 GB and stays inside that rounding step."""
        page = MagicMock()
        page.evaluate.return_value = {"space": "0.01 GB", "fileFolder": "2"}
        errors = workspace_storage_mismatches(
            page,
            {"num_files": 2, "file_size": "14.5 MB"},
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
