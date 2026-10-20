"""Tests for FERC catalog URL helpers and candidate rows."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from sourcing.FercCandidateFetcher import (
    AGENCY,
    FercCandidateFetcher,
    canonical_dataset_url,
    dataset_candidate_row,
    rows_from_assets,
)


class TestFercDatasetUrl(unittest.TestCase):
    """Tests for landing-page URL canonicalization."""

    def test_canonical_dataset_url_strips_slash(self) -> None:
        """Dataset pages drop a trailing slash."""
        self.assertEqual(
            canonical_dataset_url(
                "https://data.ferc.gov/annual-charges/oil-assessment-table/"
            ),
            "https://data.ferc.gov/annual-charges/oil-assessment-table",
        )

    def test_asset_page_is_not_a_dataset(self) -> None:
        """A data-asset URL has only one path segment."""
        self.assertIsNone(canonical_dataset_url("https://data.ferc.gov/annual-charges"))


class TestFercCandidateRows(unittest.TestCase):
    """Tests for flattening the data-assets payload."""

    def test_rows_from_assets_orders_by_id_and_keeps_zero(self) -> None:
        """Dataset id 0 is kept, and rows sort by id."""
        assets = [
            {
                "program_office": "Office of Tech Reporting & Economics",
                "data-sets": [
                    {
                        "id": 1,
                        "title": "Form 552 Page 3",
                        "url": "https://data.ferc.gov/form-no.-552-download-data/form-552-page-3",
                        "description": "Page 3",
                    },
                    {
                        "id": 0,
                        "title": "Form 552 Master Table",
                        "url": "https://data.ferc.gov/form-no.-552-download-data/form-552-master-table/",
                        "description": "Pages 1 and 4",
                    },
                ],
            }
        ]

        rows = rows_from_assets(assets)

        self.assertEqual([row["record_id"] for row in rows], ["0", "1"])
        self.assertEqual(rows[0]["title"], "Form 552 Master Table")
        self.assertEqual(rows[0]["office"], "Office of Tech Reporting & Economics")
        self.assertEqual(rows[0]["agency"], AGENCY)
        self.assertFalse(rows[0]["url"].endswith("/"))

    def test_dataset_without_title_is_skipped(self) -> None:
        """A dataset needs a title and a landing URL."""
        self.assertIsNone(dataset_candidate_row({"id": 4, "url": "https://data.ferc.gov/a/b"}, ""))

    def test_fetcher_lists_client_assets(self) -> None:
        """The fetcher flattens whatever the catalog client returns."""
        client = MagicMock()
        client.fetch_data_assets.return_value = [
            {
                "program_office": "Office of Energy Projects",
                "data-sets": [
                    {
                        "id": 30,
                        "title": "Active Exemptions",
                        "url": "https://data.ferc.gov/active-hydropower-projects/active-exemptions",
                        "description": "Exempted projects.",
                    }
                ],
            }
        ]

        rows = FercCandidateFetcher(client=client).list_dataset_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["record_id"], "30")
        self.assertEqual(rows[0]["summary"], "Exempted projects.")
        client.fetch_data_assets.assert_called_once()


if __name__ == "__main__":
    unittest.main()
