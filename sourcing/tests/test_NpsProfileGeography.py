"""Tests for IRMA Units/Geography mapping onto DataLumos coverage."""

from __future__ import annotations

import unittest

from sourcing.NpsProfileGeography import (
    bbox_from_wkt,
    profile_bounding_box,
    profile_geographic_coverage,
    profile_short_unit_names,
    profile_unit_names,
    short_unit_name,
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

    def test_park_units_map_to_states_even_with_wide_bbox(self) -> None:
        """Known park codes yield states when IRMA bbox is network-wide."""
        from sourcing.NpsProfileGeography import profile_states_from_units

        profile = {
            "units": [
                {"unitCode": "APHN", "unitName": "Appalachian Highlands Network"},
                {"unitCode": "BLRI", "unitName": "Blue Ridge Parkway"},
                {"unitCode": "BISO", "unitName": "Big South Fork National River and Recreation Area"},
                {"unitCode": "OBRI", "unitName": "Obed Wild and Scenic River"},
            ],
            "boundingBoxes": [
                {
                    "wkt": (
                        "POLYGON (("
                        "-85.5 35.0, -78.7 35.0, -78.7 38.1, -85.5 38.1, -85.5 35.0"
                        "))"
                    )
                }
            ],
        }
        self.assertEqual(
            profile_states_from_units(profile),
            ["North Carolina", "Virginia", "Kentucky", "Tennessee"],
        )
        coverage = profile_geographic_coverage(profile)
        self.assertNotIn("United States", coverage)
        for state in ("North Carolina", "Virginia", "Kentucky", "Tennessee"):
            self.assertIn(state, coverage)

    def test_network_unit_alone_does_not_add_states(self) -> None:
        """APHN is a network, not a park place."""
        from sourcing.NpsProfileGeography import profile_states_from_units

        profile = {
            "units": [{"unitCode": "APHN", "unitName": "Appalachian Highlands Network"}],
        }
        self.assertEqual(profile_states_from_units(profile), [])

    def test_short_unit_name_strips_designation_suffixes(self) -> None:
        """NPS designation phrases are removed; the place stem remains."""
        cases = {
            "Blue Ridge Parkway": "Blue Ridge",
            "Big South Fork National River and Recreation Area": "Big South Fork",
            "Obed Wild and Scenic River": "Obed",
            "Appalachian Highlands Network": "Appalachian Highlands",
            "Yellowstone National Park": "Yellowstone",
            "Great Smoky Mountains National Park": "Great Smoky Mountains",
        }
        for full, short in cases.items():
            self.assertEqual(short_unit_name(full), short)

    def test_profile_short_unit_names_dedupes(self) -> None:
        """Short names keep IRMA order and drop duplicates."""
        profile = {
            "units": [
                {"unitCode": "APHN", "unitName": "Appalachian Highlands Network"},
                {"unitCode": "BLRI", "unitName": "Blue Ridge Parkway"},
                {"unitCode": "OBRI", "unitName": "Obed Wild and Scenic River"},
            ]
        }
        self.assertEqual(
            profile_short_unit_names(profile),
            ["Appalachian Highlands", "Blue Ridge", "Obed"],
        )


if __name__ == "__main__":
    unittest.main()
