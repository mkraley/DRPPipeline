"""Unit tests for sheet_column_utils."""

import unittest

from utils.sheet_column_utils import (
    find_column_by_prefix,
    normalize_sheet_header,
    require_column_by_prefix,
    row_value_by_column_prefix,
)


class TestSheetColumnUtils(unittest.TestCase):
    """Tests for inventory sheet column header matching."""

    def test_normalize_sheet_header(self) -> None:
        """Test header normalization trims and lowercases."""
        self.assertEqual(normalize_sheet_header("  Download Location "), "download location")

    def test_find_column_by_prefix_exact_and_long_header(self) -> None:
        """Test prefix match for short and long Download Location headers."""
        fieldnames = [
            "URL",
            "Download Location",
            "Download Location (where is the rescued data in datalumos?)",
        ]
        self.assertEqual(find_column_by_prefix(fieldnames, "Download Location"), "Download Location")
        long_only = ["URL", "Download Location (where is the rescued data in datalumos?)"]
        self.assertEqual(
            find_column_by_prefix(long_only, "Download Location"),
            "Download Location (where is the rescued data in datalumos?)",
        )

    def test_find_column_by_prefix_no_match(self) -> None:
        """Test None when no header starts with the prefix."""
        self.assertIsNone(find_column_by_prefix(["URL", "Notes"], "Download Location"))

    def test_row_value_by_column_prefix(self) -> None:
        """Test reading a row value via header prefix."""
        row = {
            "URL": "https://example.com/x",
            "Download Location (where is the rescued data in datalumos?)": "  https://dl.example/1  ",
        }
        self.assertEqual(
            row_value_by_column_prefix(row, "Download Location"),
            "https://dl.example/1",
        )

    def test_require_column_by_prefix_raises(self) -> None:
        """Test require_column_by_prefix raises when prefix is missing."""
        with self.assertRaises(ValueError) as cm:
            require_column_by_prefix(["URL"], "Download Location")
        self.assertIn("Download Location", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
