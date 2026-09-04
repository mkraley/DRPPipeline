"""Unit tests for utils.title_utils."""

import unittest

from utils.title_utils import (
    normalize_inventory_title,
    prepare_datalumos_title,
    truncate_title_for_datalumos,
)


class TestNormalizeInventoryTitle(unittest.TestCase):
    """Tests for catalog title suffix stripping."""

    def test_strips_ahrq_suffix(self) -> None:
        raw = "Hospital Survey Data | Agency for Healthcare Research and Quality"
        self.assertEqual(normalize_inventory_title(raw), "Hospital Survey Data")

    def test_strips_suffix_case_insensitive(self) -> None:
        raw = "Dataset X | agency for healthcare research and quality"
        self.assertEqual(normalize_inventory_title(raw), "Dataset X")

    def test_strips_medicaid_suffix(self) -> None:
        raw = "Adult Health Care Quality Measures | Medicaid"
        self.assertEqual(normalize_inventory_title(raw), "Adult Health Care Quality Measures")

    def test_strips_both_suffixes_when_present(self) -> None:
        raw = "Dataset | Medicaid | Agency for Healthcare Research and Quality"
        self.assertEqual(normalize_inventory_title(raw), "Dataset")

    def test_leaves_title_without_suffix(self) -> None:
        self.assertEqual(normalize_inventory_title("Plain Title"), "Plain Title")

    def test_empty_and_none(self) -> None:
        self.assertEqual(normalize_inventory_title(""), "")
        self.assertEqual(normalize_inventory_title(None), "")

    def test_does_not_strip_embedded_pipe(self) -> None:
        raw = "Part A | Part B | Agency for Healthcare Research and Quality"
        self.assertEqual(normalize_inventory_title(raw), "Part A | Part B")


class TestPrepareDatalumosTitle(unittest.TestCase):
    """Tests for DataLumos title preparation helpers."""

    def test_prepare_datalumos_title_replaces_colons(self) -> None:
        """Colon-space separators become em dashes."""
        self.assertEqual(
            prepare_datalumos_title("Atlas Databases: 2003"),
            "Atlas Databases — 2003",
        )

    def test_truncate_title_for_datalumos_unchanged_when_short(self) -> None:
        """Short titles pass through."""
        self.assertEqual(truncate_title_for_datalumos("Short"), "Short")
