"""Tests for DataGovCatalogClient."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.DataGovCatalogClient import DataGovCatalogClient
from utils.Args import Args


class TestDataGovCatalogClient(unittest.TestCase):
    """Tests for GSA Catalog API paging."""

    def setUp(self) -> None:
        """Initialize Args for client construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "datagov_catalog_client"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_missing_org_slug_raises(self) -> None:
        """org_slug is required."""
        with self.assertRaises(ValueError):
            DataGovCatalogClient(org_slug="  ")

    def test_missing_api_key_raises(self) -> None:
        """fetch_search_page requires gsa_api_key."""
        client = DataGovCatalogClient(org_slug="epa", api_key="")
        with self.assertRaises(ValueError):
            client.fetch_search_page()

    @patch("sourcing.DataGovCatalogClient.requests.get")
    def test_fetch_search_page_sends_key_and_org(self, mock_get: MagicMock) -> None:
        """First page requests the configured org with the API key."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [], "sort": "last_harvested_date"}
        mock_get.return_value = response

        payload = DataGovCatalogClient(
            org_slug="epa",
            api_key="test-key",
        ).fetch_search_page()

        self.assertEqual(payload["results"], [])
        mock_get.assert_called_once()
        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "test-key")
        self.assertEqual(kwargs["params"]["org_slug"], "epa")
        self.assertNotIn("after", kwargs["params"])

    @patch("sourcing.DataGovCatalogClient.requests.get")
    def test_fetch_search_page_passes_after_cursor(self, mock_get: MagicMock) -> None:
        """Subsequent pages send the after cursor."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [{"slug": "x"}], "after": "next"}
        mock_get.return_value = response

        DataGovCatalogClient(org_slug="ssa", api_key="k").fetch_search_page(
            after="cursor-1"
        )

        self.assertEqual(mock_get.call_args.kwargs["params"]["after"], "cursor-1")

    @patch("sourcing.DataGovCatalogClient.requests.get")
    def test_rate_limit_raises_runtime_error(self, mock_get: MagicMock) -> None:
        """HTTP 429 becomes a RuntimeError."""
        response = MagicMock()
        response.status_code = 429
        response.text = "Too Many Requests"
        mock_get.return_value = response

        with self.assertRaises(RuntimeError) as ctx:
            DataGovCatalogClient(org_slug="epa", api_key="k").fetch_search_page()
        self.assertIn("429", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
