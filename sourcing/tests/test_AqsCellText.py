"""Tests for AirData column text helpers."""

from __future__ import annotations

import unittest

from sourcing.AqsCellText import is_explicit_zero, series_from_bucket


class TestAqsCellText(unittest.TestCase):
    """Size checks and series ids."""

    def test_explicit_zero_matches_only_a_zero_kb_label(self) -> None:
        """0 KB is empty; a positive size is kept."""
        self.assertTrue(is_explicit_zero("0 Rows 0 KB"))
        self.assertFalse(is_explicit_zero("10 Rows 1,351 KB"))

    def test_ambiguous_prefixes_are_skipped(self) -> None:
        """A column whose zips do not share one prefix is not a series."""
        bucket = {
            "files": [],
            "advisories": [],
            "prefixes": ["daily_44201", "daily_42401"],
            "omitted": 0,
        }
        self.assertIsNone(series_from_bucket("Daily Summary Data", "Ozone", bucket))

    def test_column_with_only_empty_files_is_skipped(self) -> None:
        """A column whose zips are all 0 KB is not a project."""
        bucket = {
            "files": [],
            "advisories": [],
            "prefixes": ["hourly_LEAD"],
            "omitted": 47,
        }
        self.assertIsNone(series_from_bucket("Hourly Data", "Lead", bucket))


if __name__ == "__main__":
    unittest.main()