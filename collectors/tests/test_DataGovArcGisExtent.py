"""Tests for ArcGIS MapServer/FeatureServer extent helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from collectors.DataGovArcGisExtent import (
    arcgis_json_url,
    bounding_box_from_arcgis_extent,
    fetch_arcgis_service_extent,
    first_arcgis_extent_from_urls,
    is_arcgis_hub_or_item_page,
    is_arcgis_map_or_feature_server,
    web_mercator_to_lon_lat,
)


class TestDataGovArcGisExtent(unittest.TestCase):
    """Tests for ArcGIS REST extent parsing and URL classification."""

    def test_classifies_map_and_feature_servers(self) -> None:
        """MapServer/FeatureServer paths are recognized; hub pages are not."""
        self.assertTrue(
            is_arcgis_map_or_feature_server(
                "https://services.arcgis.com/org/arcgis/rest/services/FRS/FeatureServer"
            )
        )
        self.assertTrue(
            is_arcgis_map_or_feature_server(
                "https://gispub.epa.gov/arcgis/rest/services/OEI/FRS_PowerPlants/MapServer"
            )
        )
        self.assertFalse(
            is_arcgis_map_or_feature_server("https://www.epa.gov/frs")
        )

    def test_classifies_hub_and_item_pages(self) -> None:
        """Interactive ArcGIS hub/item pages are flagged for PDF skip."""
        self.assertTrue(
            is_arcgis_hub_or_item_page(
                "https://edg-epa.hub.arcgis.com/datasets/3c8a335f4b5243a188fd75472459e567/about"
            )
        )
        self.assertTrue(
            is_arcgis_hub_or_item_page(
                "https://epa.maps.arcgis.com/home/item.html?id=3c8a335f4b5243a188fd75472459e567"
            )
        )
        self.assertFalse(
            is_arcgis_hub_or_item_page(
                "https://services.arcgis.com/org/arcgis/rest/services/FRS/FeatureServer"
            )
        )

    def test_arcgis_json_url_sets_f_json(self) -> None:
        """Service metadata requests use f=json."""
        self.assertEqual(
            arcgis_json_url(
                "https://services.arcgis.com/org/arcgis/rest/services/FRS/FeatureServer"
            ),
            "https://services.arcgis.com/org/arcgis/rest/services/FRS/FeatureServer?f=json",
        )

    def test_web_mercator_to_lon_lat_origin(self) -> None:
        """Web Mercator (0,0) maps near lon/lat origin."""
        lon, lat = web_mercator_to_lon_lat(0.0, 0.0)
        self.assertAlmostEqual(lon, 0.0, places=5)
        self.assertAlmostEqual(lat, 0.0, places=5)

    def test_bounding_box_from_geographic_extent(self) -> None:
        """NAD83 / WGS84 extents keep degree coordinates."""
        box = bounding_box_from_arcgis_extent(
            {
                "xmin": -162.8,
                "ymin": 17.7,
                "xmax": -2.0,
                "ymax": 70.3,
                "spatialReference": {"wkid": 4269, "latestWkid": 4269},
            }
        )
        assert box is not None
        self.assertAlmostEqual(box["west"], -162.8)
        self.assertAlmostEqual(box["east"], -2.0)
        self.assertAlmostEqual(box["south"], 17.7)
        self.assertAlmostEqual(box["north"], 70.3)

    def test_bounding_box_from_web_mercator_extent(self) -> None:
        """Web Mercator meter extents are reprojected to lon/lat."""
        box = bounding_box_from_arcgis_extent(
            {
                "xmin": -20037508.34,
                "ymin": -20037508.34,
                "xmax": 20037508.34,
                "ymax": 20037508.34,
                "spatialReference": {"wkid": 3857, "latestWkid": 3857},
            }
        )
        assert box is not None
        self.assertLess(box["west"], -170.0)
        self.assertGreater(box["east"], 170.0)

    @patch("collectors.DataGovArcGisExtent.requests.get")
    def test_fetch_arcgis_service_extent_reads_full_extent(
        self,
        mock_get: MagicMock,
    ) -> None:
        """Service JSON fullExtent becomes a WGS84 bbox."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "fullExtent": {
                "xmin": -162.8,
                "ymin": 17.7,
                "xmax": -2.0,
                "ymax": 70.3,
                "spatialReference": {"wkid": 4269},
            }
        }
        mock_get.return_value = response
        box = fetch_arcgis_service_extent(
            "https://services.arcgis.com/org/arcgis/rest/services/FRS/FeatureServer"
        )
        assert box is not None
        self.assertAlmostEqual(box["west"], -162.8)
        mock_get.assert_called_once()
        self.assertIn("f=json", mock_get.call_args.args[0])

    @patch("collectors.DataGovArcGisExtent.fetch_arcgis_service_extent")
    def test_first_arcgis_extent_from_urls_skips_non_services(
        self,
        mock_fetch: MagicMock,
    ) -> None:
        """Non-service URLs are ignored; first service extent wins."""
        mock_fetch.side_effect = (
            lambda url: {
                "west": -100.0,
                "east": -80.0,
                "south": 30.0,
                "north": 40.0,
            }
            if "FeatureServer" in url
            else None
        )
        box = first_arcgis_extent_from_urls(
            [
                "https://www.epa.gov/frs",
                "https://services.arcgis.com/org/arcgis/rest/services/FRS/FeatureServer",
            ]
        )
        assert box is not None
        self.assertEqual(box["west"], -100.0)
        self.assertEqual(mock_fetch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
