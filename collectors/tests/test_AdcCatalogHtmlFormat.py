"""Tests for AdcCatalogHtmlFormat helpers."""

from __future__ import annotations

import unittest

from collectors.AdcCatalogHtmlFormat import humanize_relation


class TestAdcCatalogHtmlFormat(unittest.TestCase):
    """Tests for catalog HTML formatting helpers."""

    def test_humanize_relation_known_code(self) -> None:
        """Known Figshare relation codes map to readable labels."""
        self.assertEqual(humanize_relation("IsSupplementTo"), "Is supplement to")

    def test_humanize_relation_unknown_code(self) -> None:
        """Unknown relation codes are spaced for readability."""
        self.assertEqual(humanize_relation("IsDerivedFrom"), "Is Derived From")
