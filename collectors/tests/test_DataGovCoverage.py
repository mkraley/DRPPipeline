"""Tests for Data.gov geographic and temporal coverage helpers."""

from __future__ import annotations

import unittest

from collectors.DataGovCoverage import (
    bounding_box_from_csv,
    catalog_date,
    catalog_temporal_fields,
    looks_like_coordinates,
    normalize_catalog_geographic,
)


class TestDataGovCoverage(unittest.TestCase):
    """Tests for ICPSR geographic mapping and issued/modified temporal fallback."""

    def test_looks_like_coordinates(self) -> None:
        """Numeric CSV strings are coordinates; place names are not."""
        self.assertTrue(
            looks_like_coordinates("-68.325538,18.9742,-166.479506,67.08798")
        )
        self.assertFalse(looks_like_coordinates("United States"))

    def test_bounding_box_from_csv_orders_axes(self) -> None:
        """Four-number spatial CSV becomes a min/max bounding box."""
        box = bounding_box_from_csv("-68.325538,18.9742,-166.479506,67.08798")
        assert box is not None
        self.assertAlmostEqual(box["west"], -166.479506)
        self.assertAlmostEqual(box["east"], -68.325538)
        self.assertAlmostEqual(box["south"], 18.9742)
        self.assertAlmostEqual(box["north"], 67.08798)

    def test_normalize_catalog_geographic_bbox_to_united_states(self) -> None:
        """Continental bbox strings map to United States, not raw coordinates."""
        geo = normalize_catalog_geographic(
            "-68.325538,18.9742,-166.479506,67.08798"
        )
        self.assertEqual(geo.geographic_coverage, "United States")
        self.assertNotIn(",", geo.geographic_coverage)

    def test_normalize_catalog_geographic_place_label(self) -> None:
        """Place labels resolve through the ICPSR thesaurus."""
        geo = normalize_catalog_geographic(
            [{"@type": "Location", "prefLabel": "United States"}]
        )
        self.assertEqual(geo.geographic_coverage, "United States")

    def test_normalize_catalog_geographic_omits_unresolvable_coords(self) -> None:
        """Coordinates that cannot map to vocabulary terms are omitted."""
        geo = normalize_catalog_geographic("0.0,0.0,0.1,0.1")
        self.assertEqual(geo.geographic_coverage, "")

    def test_catalog_date_strips_timestamp(self) -> None:
        """ISO timestamps reduce to calendar dates."""
        self.assertEqual(catalog_date("2025-06-03T00:00:00.000+00:00"), "2025-06-03")

    def test_catalog_temporal_prefers_temporal_coverage(self) -> None:
        """Explicit temporalCoverage wins over issued/modified."""
        fields = catalog_temporal_fields(
            title="Example",
            dataset={
                "temporalCoverage": "1880/2025",
                "datePublished": "2020-01-01",
                "dateModified": "2026-01-01",
            },
        )
        self.assertEqual(fields["time_start"], "1880")
        self.assertEqual(fields["time_end"], "2025")

    def test_catalog_temporal_falls_back_to_issued_modified(self) -> None:
        """When temporal coverage is absent, issued/modified set the range."""
        fields = catalog_temporal_fields(
            title="Example",
            dataset={
                "datePublished": "2020-01-08T00:00:00.000+00:00",
                "dateModified": "2026-10-25T22:39:41.000+00:00",
            },
            complete_rows={
                "issued": "2020-01-08T00:00:00.000+00:00",
                "modified": "2026-10-25T22:39:41.000+00:00",
            },
        )
        self.assertEqual(fields["time_start"], "2020-01-08")
        self.assertEqual(fields["time_end"], "2026-10-25")


if __name__ == "__main__":
    unittest.main()
