"""Tests for Clip and Ship item metadata."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from collectors.EpaHubItem import (
    EpaHubItemClient,
    bbox_from_geometry,
    metadata_from_feature,
    service_url_from_feature,
)
from utils.datalumos_data_types import DATA_TYPE_GIS

_ITEM = "27cd1f0c43904460b27e9ab21449519b"


class TestEpaHubItem(unittest.TestCase):
    """Tests for fetching and mapping one Hub feature."""

    def test_fetch_feature_reads_item_json(self) -> None:
        """The item URL is the collection items endpoint plus the id."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"id": _ITEM, "properties": {"title": "NPL"}}
        seen: list[str] = []

        def getter(url: str, **_kwargs: object) -> MagicMock:
            seen.append(url)
            return response

        feature = EpaHubItemClient(
            getter=getter,
            items_url="https://edg-epa.hub.arcgis.com/api/search/v1/collections/all/items",
        ).fetch_feature(_ITEM)
        self.assertEqual(feature["id"], _ITEM)
        self.assertTrue(seen[0].endswith(f"/items/{_ITEM}"))

    def test_metadata_and_service_url(self) -> None:
        """Feature services keep GIS type, keywords, and the service URL."""
        feature = {
            "id": _ITEM,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-10.0, 1.0], [-9.0, 2.0]]],
            },
            "properties": {
                "title": "NPL",
                "type": "Feature Service",
                "snippet": "Bounds",
                "source": "Office of Water",
                "tags": ["Superfund"],
                "url": "https://services.arcgis.com/org/arcgis/rest/services/NPL/FeatureServer",
            },
        }
        fields = metadata_from_feature(feature)
        self.assertEqual(fields["data_types"], DATA_TYPE_GIS)
        self.assertEqual(fields["keywords"], "Superfund")
        self.assertIn("FeatureServer", service_url_from_feature(feature))
        box = bbox_from_geometry(feature["geometry"])
        self.assertEqual(box["west"], -10.0)
        self.assertEqual(box["north"], 2.0)


if __name__ == "__main__":
    unittest.main()
