"""Tests for EDG Clip and Ship candidate rows."""

from __future__ import annotations

import unittest

from sourcing.EpaHubCandidateFetcher import (
    hub_item_url,
    item_id_from_source_url,
    row_from_feature,
    rows_from_features,
)
from sourcing.EpaSourcing import AGENCY

_FEATURE_ID = "27cd1f0c43904460b27e9ab21449519b"
_PAGE_ID = "acc4a8f4aadf4e38941bf933bfd968fd"
_SERVICE_ID = "984aaa5d4b1f4dd6b738cac96b282514"


def _feature(item_id: str, title: str, item_type: str) -> dict:
    """Return a minimal Hub feature."""
    return {
        "id": item_id,
        "properties": {
            "title": title,
            "type": item_type,
            "snippet": "  Line one\nline two  ",
            "source": "U.S. EPA Office of Water",
        },
    }


class TestEpaHubCandidateRows(unittest.TestCase):
    """Tests for Hub feature to sourcing-row conversion."""

    def test_feature_service_uses_datasets_path(self) -> None:
        """Feature services link to the Hub dataset page."""
        row = row_from_feature(_feature(_FEATURE_ID, "NPL Boundaries", "Feature Service"))
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["url"], hub_item_url(_FEATURE_ID, "Feature Service"))
        self.assertEqual(
            row["url"],
            f"https://edg-epa.hub.arcgis.com/datasets/{_FEATURE_ID}",
        )
        self.assertEqual(row["agency"], AGENCY)
        self.assertEqual(row["office"], "U.S. EPA Office of Water")
        self.assertEqual(row["summary"], "Line one line two")

    def test_service_definition_and_hub_page_paths(self) -> None:
        """Service definitions and hub pages use their Hub sections."""
        self.assertTrue(
            hub_item_url(_SERVICE_ID, "Service Definition").endswith(
                f"/documents/{_SERVICE_ID}"
            )
        )
        self.assertTrue(hub_item_url(_PAGE_ID, "Hub Page").endswith(f"/pages/{_PAGE_ID}"))

    def test_item_id_from_item_page_query(self) -> None:
        """An ArcGIS item page query id matches the Hub path id."""
        url = f"https://epa.maps.arcgis.com/home/item.html?id={_FEATURE_ID}"
        self.assertEqual(item_id_from_source_url(url), _FEATURE_ID)
        self.assertIsNone(item_id_from_source_url("https://catalog.data.gov/dataset/air"))

    def test_rows_skip_duplicates_and_sort_by_title(self) -> None:
        """Duplicate ids are dropped and rows sort by title."""
        features = [
            _feature(_FEATURE_ID, "Zebra", "Feature Service"),
            _feature(_FEATURE_ID, "Zebra copy", "Feature Service"),
            _feature(_PAGE_ID, "alpha help", "Hub Page"),
            {"id": "not-an-id", "properties": {"title": "Bad"}},
        ]
        rows = rows_from_features(features)
        self.assertEqual([row["title"] for row in rows], ["alpha help", "Zebra"])

    def test_missing_title_is_skipped(self) -> None:
        """A feature without a title is not a candidate."""
        feature = _feature(_FEATURE_ID, "   ", "Feature Service")
        self.assertIsNone(row_from_feature(feature))


if __name__ == "__main__":
    unittest.main()
