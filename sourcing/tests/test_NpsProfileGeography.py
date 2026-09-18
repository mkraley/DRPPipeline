"""Tests for IRMA Units/Geography mapping onto DataLumos coverage."""

from __future__ import annotations

import unittest

from sourcing.NpsProfileGeography import (
    bbox_from_wkt,
    profile_bounding_box,
    profile_geographic_coverage,
    profile_unit_names,
)

_NC_WKT = (
    "POLYGON ((-79.1 35.5, -78.5 35.5, -78.5 36.0, -79.1 36.0, -79.1 35.5))"
)


class TestNpsProfileGeography(unittest.TestCase):
    """Tests for WKT bounding boxes and unit names."""

    def test_bbox_from_wkt_reads_polygon_corners(self) -> None:
        """IRMA POLYGON WKT becomes west/east/south/north."""
        box = bbox_from_wkt(_NC_WKT)
        self.assertIsNotNone(box)
        assert box is not None
        self.assertAlmostEqual(box["west"], -79.1)
        self.assertAlmostEqual(box["east"], -78.5)
        self.assertAlmostEqual(box["south"], 35.5)
        self.assertAlmostEqual(box["north"], 36.0)

    def test_profile_bounding_box_unions_polygons(self) -> None:
        """Multiple Geography polygons are unioned."""
        profile = {
            "boundingBoxes": [
                {"wkt": _NC_WKT},
                {"wkt": "POLYGON ((-81.0 36.2, -80.0 36.2, -80.0 37.0, -81.0 37.0, -81.0 36.2))"},
            ]
        }
        box = profile_bounding_box(profile)
        self.assertIsNotNone(box)
        assert box is not None
        self.assertAlmostEqual(box["west"], -81.0)
        self.assertAlmostEqual(box["east"], -78.5)
        self.assertAlmostEqual(box["south"], 35.5)
        self.assertAlmostEqual(box["north"], 37.0)

    def test_unit_names_and_coverage_from_geography(self) -> None:
        """Unit names plus a local bbox map onto ICPSR state coverage."""
        profile = {
            "units": [{"unitCode": "BLRI", "unitName": "Blue Ridge Parkway"}],
            "boundingBoxes": [{"wkt": _NC_WKT}],
        }
        self.assertEqual(profile_unit_names(profile), ["Blue Ridge Parkway"])
        coverage = profile_geographic_coverage(profile)
        self.assertIn("North Carolina", coverage)


if __name__ == "__main__":
    unittest.main()
