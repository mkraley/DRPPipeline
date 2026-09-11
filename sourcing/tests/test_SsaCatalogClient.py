"""Tests for SsaCatalogClient."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.SsaCatalogClient import SsaCatalogClient
from utils.Args import Args


class TestSsaCatalogClient(unittest.TestCase):
    """Tests for GSA Catalog API paging."""

    def setUp(self) -> None:
        """Initialize Args for client construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "ssa_catalog_client"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_missing_api_key_raises(self) -> None:
        """fetch_search_page requires gsa_api_key."""
        client = SsaCatalogClient(api_key="")
        with self.assertRaises(ValueError):
            client.fetch_search_page()

    @patch("sourcing.SsaCatalogClient.requests.get")
    def test_fetch_search_page_sends_key_and_org(self, mock_get: MagicMock) -> None:
        """First page requests SSA org with the configured API key."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [], "sort": "last_harvested_date"}
        mock_get.return_value = response

        payload = SsaCatalogClient(api_key="test-key").fetch_search_page()

        self.assertEqual(payload["results"], [])
        mock_get.assert_called_once()
        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "test-key")
        self.assertEqual(kwargs["params"]["org_slug"], "ssa")
        self.assertNotIn("after", kwargs["params"])

    @patch("sourcing.SsaCatalogClient.requests.get")
    def test_fetch_search_page_passes_after_cursor(self, mock_get: MagicMock) -> None:
        """Subsequent pages send the after cursor."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [{"slug": "x"}], "after": "next"}
        mock_get.return_value = response

        SsaCatalogClient(api_key="k").fetch_search_page(after="cursor-1")

        self.assertEqual(mock_get.call_args.kwargs["params"]["after"], "cursor-1")

    @patch("sourcing.SsaCatalogClient.requests.get")
    def test_rate_limit_raises_runtime_error(self, mock_get: MagicMock) -> None:
        """HTTP 429 becomes a RuntimeError."""
        response = MagicMock()
        response.status_code = 429
        response.text = "Too Many Requests"
        mock_get.return_value = response

        with self.assertRaises(RuntimeError) as ctx:
            SsaCatalogClient(api_key="k").fetch_search_page()
        self.assertIn("429", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
