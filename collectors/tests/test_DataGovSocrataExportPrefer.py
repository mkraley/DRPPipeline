"""Tests for preferring Socrata export.* over query.* downloads."""

from __future__ import annotations

import unittest

from collectors.DataGovFileDownloader import prefer_socrata_export_files
from collectors.DataGovMetadataExtractor import DataGovDownloadFile


class TestPreferSocrataExportFiles(unittest.TestCase):
    """Drop redundant query dumps when export.csv exists for the same view."""

    def test_keeps_export_drops_query_for_same_view(self) -> None:
        """query.json/xml are skipped when export.csv shares the view id."""
        files = [
            DataGovDownloadFile(
                label="JSON",
                url=(
                    "https://data.energystar.gov/api/v3/views/8wj2-sec8/"
                    "query.json?accessType=DOWNLOAD"
                ),
                filename="query.json",
            ),
            DataGovDownloadFile(
                label="XML",
                url=(
                    "https://data.energystar.gov/api/v3/views/8wj2-sec8/"
                    "query.xml?accessType=DOWNLOAD"
                ),
                filename="query.xml",
            ),
            DataGovDownloadFile(
                label="CSV",
                url=(
                    "https://data.energystar.gov/api/v3/views/8wj2-sec8/"
                    "export.csv?accessType=DOWNLOAD"
                ),
                filename="export.csv",
            ),
        ]
        kept = prefer_socrata_export_files(files)
        self.assertEqual(len(kept), 1)
        self.assertIn("export.csv", kept[0].url)

    def test_keeps_query_when_no_export(self) -> None:
        """Without an export.* sibling, query files are unchanged."""
        files = [
            DataGovDownloadFile(
                label="JSON",
                url="https://data.example.gov/api/v3/views/abc/query.json",
                filename="query.json",
            )
        ]
        self.assertEqual(prefer_socrata_export_files(files), files)


if __name__ == "__main__":
    unittest.main()
