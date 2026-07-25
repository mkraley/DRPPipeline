"""Unit tests for publisher.WorkspaceFileStats."""

import unittest
from unittest.mock import MagicMock

from publisher.WorkspaceFileStats import workspace_file_stats_from_page


class TestWorkspaceFileStats(unittest.TestCase):
    """Tests for workspace file table scraping."""

    def test_workspace_file_stats_from_page_parses_table(self) -> None:
        """Workspace scraper reads name/size from table.table-hover columns."""
        page = MagicMock()
        page.evaluate.return_value = {
            "files": [
                {"name": "a.pdf", "size": "1.0 KB"},
                {"name": "b.zip", "size": "1.0 KB"},
            ]
        }
        stats = workspace_file_stats_from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.total_bytes, 2048)
        self.assertEqual(stats.file_names, ("a.pdf", "b.zip"))

    def test_workspace_file_stats_from_page_no_rows(self) -> None:
        """Empty workspace table surfaces no_files_found."""
        page = MagicMock()
        page.evaluate.return_value = {"error": "no_files_found"}
        stats = workspace_file_stats_from_page(page)
        self.assertEqual(stats.error, "no_files_found")
        self.assertEqual(stats.file_count, 0)
