"""Tests for Data.gov catalog URL helpers and candidate row building."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from sourcing.DataGovCandidateFetcher import (
    FILE_FORMATS,
    DataGovCandidateFetcher,
    catalog_url_from_slug,
    has_collectible_file,
    is_file_download,
    is_html_url,
    is_public_dataset,
    slug_from_source_url,
)
from utils.Args import Args
from utils.Logger import Logger

_AGENCY = "Environmental Protection Agency"
_OFFICE = "Environmental Protection Agency"


def _result(
    *,
    slug: str = "air-quality",
    title: str = "Air Quality",
    access: str = "public",
    distributions: list[dict[str, str]] | None = None,
    identifier: str = "US-GOV-EPA-1",
) -> dict:
    """Build a minimal GSA search result."""
    return {
        "slug": slug,
        "title": title,
        "identifier": identifier,
        "dcat": {
            "accessLevel": access,
            "identifier": identifier,
            "distribution": distributions
            if distributions is not None
            else [
                {
                    "format": "GEOJSON",
                    "downloadURL": "https://www.epa.gov/data/air.geojson",
                }
            ],
        },
    }


class TestDataGovUrlHelpers(unittest.TestCase):
    """Tests for catalog slug helpers."""

    def test_catalog_url_from_slug(self) -> None:
        """Build canonical catalog dataset URLs."""
        self.assertEqual(
            catalog_url_from_slug("air-quality"),
            "https://catalog.data.gov/dataset/air-quality",
        )

    def test_slug_from_source_url(self) -> None:
        """Extract slugs from catalog dataset URLs."""
        self.assertEqual(
            slug_from_source_url("https://catalog.data.gov/dataset/air-quality"),
            "air-quality",
        )
        self.assertIsNone(slug_from_source_url("https://www.epa.gov/data/"))
        self.assertIsNone(
            slug_from_source_url("https://catalog.data.gov/organization/epa")
        )


class TestDataGovCollectibleFilters(unittest.TestCase):
    """Tests for public-with-file filtering."""

    def test_is_file_download_includes_geospatial_formats(self) -> None:
        """GEOJSON/TIFF/NC count; HTML landing pages do not."""
        self.assertTrue(
            is_file_download(
                {
                    "format": "GEOJSON",
                    "downloadURL": "https://www.epa.gov/x.geojson",
                }
            )
        )
        self.assertTrue(
            is_file_download(
                {"format": "TIFF", "downloadURL": "https://www.epa.gov/map.tif"}
            )
        )
        self.assertTrue(
            is_file_download(
                {"format": "", "downloadURL": "https://www.epa.gov/model.nc"}
            )
        )
        self.assertIn("GEOJSON", FILE_FORMATS)
        self.assertFalse(
            is_file_download(
                {
                    "format": "HTML",
                    "downloadURL": "https://www.epa.gov/index.html",
                }
            )
        )
        self.assertFalse(is_file_download({"format": "CSV", "accessURL": "https://x"}))

    def test_is_html_url(self) -> None:
        """HTML format labels and .html suffixes are landing pages."""
        self.assertTrue(is_html_url("https://www.epa.gov/x.html", "HTML"))
        self.assertFalse(is_html_url("https://www.epa.gov/map.geojson", "GEOJSON"))

    def test_html_only_is_not_collectible(self) -> None:
        """Public HTML-only rows are skipped."""
        result = _result(
            distributions=[
                {
                    "format": "HTML",
                    "downloadURL": "https://www.epa.gov/data/index.html",
                }
            ]
        )
        self.assertTrue(is_public_dataset(result))
        self.assertFalse(has_collectible_file(result))

    def test_restricted_with_file_is_not_public(self) -> None:
        """Restricted-public inventory rows are skipped."""
        result = _result(access="restricted public")
        self.assertFalse(is_public_dataset(result))


class TestDataGovCandidateFetcher(unittest.TestCase):
    """Tests for candidate row construction and paging."""

    def setUp(self) -> None:
        """Initialize Args defaults for fetcher construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "datagov_candidate_fetcher"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def _fetcher(self, client: MagicMock | None = None) -> DataGovCandidateFetcher:
        """Build a fetcher with EPA labels."""
        return DataGovCandidateFetcher(
            agency=_AGENCY,
            office=_OFFICE,
            client=client or MagicMock(),
            request_delay=0,
            source_label="EPA",
        )

    def test_build_candidate_row_maps_catalog_url(self) -> None:
        """Collectible hits map to catalog.data.gov dataset URLs."""
        row = self._fetcher().build_candidate_row(_result())
        assert row is not None
        self.assertEqual(row["url"], "https://catalog.data.gov/dataset/air-quality")
        self.assertEqual(row["title"], "Air Quality")
        self.assertEqual(row["record_id"], "air-quality")
        self.assertEqual(row["identifier"], "US-GOV-EPA-1")
        self.assertEqual(row["agency"], _AGENCY)

    def test_build_candidate_row_skips_html_only(self) -> None:
        """HTML-only public rows return None."""
        result = _result(
            distributions=[
                {"format": "HTML", "downloadURL": "https://www.epa.gov/x.html"}
            ]
        )
        self.assertIsNone(self._fetcher().build_candidate_row(result))

    def test_build_candidate_row_skips_non_public(self) -> None:
        """Non-public rows return None even when a file is listed."""
        self.assertIsNone(
            self._fetcher().build_candidate_row(_result(access="non-public"))
        )

    def test_list_dataset_rows_paginates_until_no_after(self) -> None:
        """Fetcher follows after cursors and skips non-collectible hits."""
        client = MagicMock()
        client.org_slug = "epa"
        client.fetch_search_page.side_effect = [
            {
                "results": [
                    _result(slug="keep-me", title="Keep"),
                    _result(
                        slug="html-only",
                        title="Index",
                        distributions=[
                            {
                                "format": "HTML",
                                "downloadURL": "https://www.epa.gov/index.html",
                            }
                        ],
                    ),
                ],
                "after": "cursor-2",
            },
            {
                "results": [_result(slug="year-2025", title="Year 2025")],
            },
        ]
        rows = self._fetcher(client).list_dataset_rows()
        self.assertEqual([row["record_id"] for row in rows], ["keep-me", "year-2025"])
        self.assertEqual(client.fetch_search_page.call_count, 2)


if __name__ == "__main__":
    unittest.main()
