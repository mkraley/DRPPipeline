"""Tests for ArcGIS extent fallback on DataGovCollector."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from collectors.DataGovCollector import DataGovCollector
from collectors.DataGovMetadataExtractor import DataGovDownloadFile
from utils.Args import Args
from utils.Logger import Logger


class TestDataGovCollectorArcgisGeo(unittest.TestCase):
    """Tests for enriching geographic coverage from ArcGIS service extents."""

    def setUp(self) -> None:
        """Initialize Args/Logger for collector construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.collector = DataGovCollector(
            source_label="EPA",
            agency="Environmental Protection Agency",
            office="Environmental Protection Agency",
            headless=True,
        )

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("collectors.DataGovCollector.first_arcgis_extent_from_urls")
    @patch("collectors.DataGovCollector.normalize_geographic_metadata")
    def test_enrich_geographic_from_arcgis_when_missing(
        self,
        mock_normalize: MagicMock,
        mock_extent: MagicMock,
    ) -> None:
        """Missing catalog spatial uses FeatureServer extent → ICPSR terms."""
        mock_extent.return_value = {
            "west": -162.8,
            "east": -2.0,
            "south": 17.7,
            "north": 70.3,
        }
        mock_normalize.return_value = MagicMock(
            geographic_coverage="United States",
            warnings=[],
        )
        parsed: dict = {
            "_html_resources": [
                DataGovDownloadFile(
                    label="Feature service",
                    url=(
                        "https://services.arcgis.com/org/arcgis/rest/services/"
                        "FRS_INTERESTS_TSCA/FeatureServer"
                    ),
                    filename="FeatureServer",
                )
            ],
            "_download_files": [],
        }
        self.collector._enrich_geographic_from_arcgis(parsed)
        self.assertEqual(parsed["geographic_coverage"], "United States")
        mock_normalize.assert_called_once()
        self.assertEqual(
            mock_normalize.call_args.kwargs["bounding_box"]["west"],
            -162.8,
        )

    @patch("collectors.DataGovCollector.first_arcgis_extent_from_urls")
    def test_enrich_skips_when_coverage_already_set(
        self,
        mock_extent: MagicMock,
    ) -> None:
        """Existing catalog-derived coverage is left alone."""
        parsed = {"geographic_coverage": "California", "_html_resources": []}
        self.collector._enrich_geographic_from_arcgis(parsed)
        mock_extent.assert_not_called()
        self.assertEqual(parsed["geographic_coverage"], "California")


if __name__ == "__main__":
    unittest.main()
