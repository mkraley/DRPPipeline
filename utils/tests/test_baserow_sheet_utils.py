"""
Unit tests for baserow_sheet_utils.
"""

import unittest

from utils.baserow_sheet_utils import (
    baserow_organization,
    format_baserow_backup_title,
    format_baserow_file_extensions,
    format_dataset_size_gb_jedec,
    website_from_source_url,
)


class TestBaserowSheetUtils(unittest.TestCase):
    """Tests for Baserow batch import value helpers."""

    def test_website_from_source_url_strips_www(self) -> None:
        """Hostname drops leading www."""
        url = "https://www.fs.usda.gov/rds/archive/catalog/RDS-2025-0009"
        self.assertEqual(website_from_source_url(url), "fs.usda.gov")

    def test_website_from_source_url_subdomain(self) -> None:
        """Non-www hostnames are preserved."""
        url = "https://rosap.ntl.bts.gov/view/dot/54854"
        self.assertEqual(website_from_source_url(url), "rosap.ntl.bts.gov")

    def test_format_baserow_backup_title_quotes_commas(self) -> None:
        """Titles with commas are wrapped in double quotes."""
        self.assertEqual(format_baserow_backup_title("A, B"), '"A, B"')

    def test_format_baserow_backup_title_plain(self) -> None:
        """Simple titles pass through unchanged."""
        self.assertEqual(format_baserow_backup_title("Plain title"), "Plain title")

    def test_format_baserow_file_extensions(self) -> None:
        """Extensions become lowercase comma-separated tokens without spaces."""
        self.assertEqual(format_baserow_file_extensions("csv, zip PDF"), "csv,zip,pdf")

    def test_format_dataset_size_gb_jedec(self) -> None:
        """Byte counts convert to floating-point binary GB."""
        self.assertEqual(format_dataset_size_gb_jedec(1024**3), "1.0")
        self.assertEqual(format_dataset_size_gb_jedec("1048576"), "0.000977")
        self.assertEqual(format_dataset_size_gb_jedec(0), "0.0")

    def test_baserow_contact_value_prefers_configured_email(self) -> None:
        """Configured baserow_contact wins over google_username."""
        from utils.baserow_sheet_utils import baserow_contact_value

        self.assertEqual(
            baserow_contact_value(
                baserow_contact="mike@kraley.com",
                google_username="mkraley",
            ),
            "mike@kraley.com",
        )

    def test_baserow_organization_prefers_office(self) -> None:
        """Organization uses office when present."""
        self.assertEqual(baserow_organization("DOT", "BTS"), "BTS")

    def test_baserow_organization_falls_back_to_agency(self) -> None:
        """Organization repeats agency when office is blank."""
        self.assertEqual(baserow_organization("DOT", ""), "DOT")
