"""Tests for new-source inventory sheet defaults."""

from __future__ import annotations

import unittest
from pathlib import Path

from utils.source_sheet_defaults import (
    DEFAULT_BASEROW_CONTACT,
    NEW_SOURCE_INVENTORY_SHEET_FORMAT,
    new_source_sheet_defaults,
)


class TestNewSourceSheetDefaults(unittest.TestCase):
    """Tests for Baserow defaults applied when creating a source."""

    def test_defaults_match_bts_style_sheet_keys(self) -> None:
        """New sources use Baserow batch import with metadata-available no."""
        defaults = new_source_sheet_defaults()
        self.assertEqual(
            defaults["inventory_sheet_format"],
            NEW_SOURCE_INVENTORY_SHEET_FORMAT,
        )
        self.assertEqual(defaults["baserow_contact"], DEFAULT_BASEROW_CONTACT)
        self.assertIs(defaults["default_metadata_available"], False)

    def test_contact_override(self) -> None:
        """A non-empty contact replaces the default email."""
        defaults = new_source_sheet_defaults(contact="owner@example.com")
        self.assertEqual(defaults["baserow_contact"], "owner@example.com")

    def test_setup_applies_new_source_defaults(self) -> None:
        """The setup wizard merges these keys into a newly written config."""
        setup_text = Path(__file__).resolve().parents[2].joinpath("setup", "Setup.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("new_source_sheet_defaults", setup_text)


if __name__ == "__main__":
    unittest.main()
