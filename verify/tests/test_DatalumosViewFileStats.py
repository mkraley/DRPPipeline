"""
Unit tests for DatalumosViewFileStats.
"""

import unittest
from unittest.mock import MagicMock

from verify.DatalumosViewFileStats import (
    DatalumosViewFileStats,
    format_verify_success_message,
    set_records_per_page,
    sizes_within_tolerance,
    sum_sizes_text,
    verify_upload_counts,
)


class TestDatalumosViewFileStats(unittest.TestCase):
    """Tests for view page stat extraction and comparison."""

    def test_sum_sizes_text(self) -> None:
        """Test summing human-readable size strings."""
        self.assertEqual(sum_sizes_text(["1.0 MB", "500 B"]), 1024 * 1024 + 500)
        self.assertIsNone(sum_sizes_text(["1.0 MB", "bad"]))

    def test_sizes_within_tolerance(self) -> None:
        """Test relative size tolerance (default 5%)."""
        self.assertTrue(sizes_within_tolerance(1000, 1040))
        self.assertTrue(sizes_within_tolerance(1000, 960))
        self.assertFalse(sizes_within_tolerance(1000, 1060))
        self.assertTrue(sizes_within_tolerance(0, 0))
        self.assertFalse(sizes_within_tolerance(0, 1))

    def test_verify_upload_counts_ok(self) -> None:
        """Test matching database and page stats produce no errors."""
        page_stats = DatalumosViewFileStats(file_count=3, total_bytes=1024)
        errors = verify_upload_counts(3, "1024", page_stats)
        self.assertEqual(errors, [])

    def test_verify_upload_counts_file_count_mismatch(self) -> None:
        """Test file count mismatch is reported."""
        page_stats = DatalumosViewFileStats(file_count=2, total_bytes=1024)
        errors = verify_upload_counts(3, "1024", page_stats)
        self.assertEqual(len(errors), 1)
        self.assertIn("file count mismatch", errors[0])

    def test_verify_upload_counts_size_mismatch(self) -> None:
        """Test file size mismatch beyond tolerance is reported."""
        page_stats = DatalumosViewFileStats(file_count=1, total_bytes=2000)
        errors = verify_upload_counts(1, "1000", page_stats)
        self.assertEqual(len(errors), 1)
        self.assertIn("file size mismatch", errors[0])

    def test_verify_upload_counts_page_error(self) -> None:
        """Test page extraction errors are reported."""
        page_stats = DatalumosViewFileStats(error="no_files_found")
        errors = verify_upload_counts(1, "1000", page_stats)
        self.assertEqual(errors, ["DataLumos page error: no_files_found"])

    def test_from_page_parses_files(self) -> None:
        """Test from_page sums sizes returned by page.evaluate."""
        page = MagicMock()
        page.evaluate.return_value = {
            "files": [
                {"name": "a.csv", "size": "1.0 KB"},
                {"name": "b.csv", "size": "1.0 KB"},
            ]
        }
        stats = DatalumosViewFileStats.from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertEqual(stats.total_bytes, 2048)

    def test_from_page_parses_view_table_layout(self) -> None:
        """Test from_page handles published view table (table-striped, Name/Size headers)."""
        page = MagicMock()
        page.evaluate.return_value = {
            "files": [
                {"name": "RDS-2026-0034.zip", "size": "184.8 MB"},
                {"name": "readme.pdf", "size": "412.3 KB"},
            ]
        }
        stats = DatalumosViewFileStats.from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 2)
        self.assertGreater(stats.total_bytes, 0)

    def test_format_verify_success_message(self) -> None:
        """Test success summary shows expected/actual files and size."""
        page_stats = DatalumosViewFileStats(file_count=5, total_bytes=194215627)
        message = format_verify_success_message(5, "185.2 MB", page_stats)
        self.assertIn("files 5/5", message)
        self.assertIn("size 185.2 MB/185.2 MB", message)

    def test_from_page_handles_error_payload(self) -> None:
        """Test from_page surfaces JS error codes."""
        page = MagicMock()
        page.evaluate.return_value = {"error": "page_not_found"}
        stats = DatalumosViewFileStats.from_page(page)
        self.assertEqual(stats.error, "page_not_found")

    def test_set_records_per_page_absent(self) -> None:
        """When the pager dropdown is missing, return False and do nothing."""
        page = MagicMock()
        page.query_selector.return_value = None
        self.assertFalse(set_records_per_page(page))
        page.wait_for_load_state.assert_not_called()

    def test_set_records_per_page_already_set(self) -> None:
        """When dropdown is already 100, do not re-select."""
        page = MagicMock()
        select = MagicMock()
        select.input_value.return_value = "100"
        page.query_selector.return_value = select
        self.assertTrue(set_records_per_page(page))
        select.select_option.assert_not_called()
        page.wait_for_load_state.assert_not_called()

    def test_set_records_per_page_selects_100(self) -> None:
        """When dropdown is present at 10, select 100 and wait for navigation."""
        page = MagicMock()
        select = MagicMock()
        select.input_value.return_value = "10"
        page.query_selector.return_value = select
        nav_cm = MagicMock()
        nav_cm.__enter__ = MagicMock(return_value=None)
        nav_cm.__exit__ = MagicMock(return_value=False)
        page.expect_navigation.return_value = nav_cm
        self.assertTrue(set_records_per_page(page))
        select.select_option.assert_called_once_with("100")
        page.expect_navigation.assert_called_once()
        page.wait_for_load_state.assert_called_once_with(
            "networkidle", timeout=120000
        )
        page.wait_for_selector.assert_called_once_with(
            "#pageSizeOptions", state="attached", timeout=60000
        )

    def test_from_page_retries_after_navigation_race(self) -> None:
        """from_page retries evaluate when the pager navigation destroys context."""
        page = MagicMock()
        page.evaluate.side_effect = [
            Exception("Page.evaluate: Execution context was destroyed, most likely because of a navigation"),
            {
                "files": [
                    {"name": "a.csv", "size": "1.0 KB"},
                ]
            },
        ]
        stats = DatalumosViewFileStats.from_page(page)
        self.assertIsNone(stats.error)
        self.assertEqual(stats.file_count, 1)
        self.assertEqual(page.evaluate.call_count, 2)
        self.assertEqual(page.wait_for_load_state.call_count, 2)


if __name__ == "__main__":
    unittest.main()
