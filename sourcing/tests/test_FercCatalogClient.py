"""Tests for FercCatalogClient."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.FercCatalogClient import FercCatalogClient
from utils.Args import Args


class TestFercCatalogClient(unittest.TestCase):
    """Tests for the FERC data-assets request."""

    def setUp(self) -> None:
        """Initialize Args for client construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "ferc_catalog_client"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_missing_api_key_raises(self) -> None:
        """fetch_data_assets requires ferc_api_key."""
        client = FercCatalogClient(api_key="")
        with self.assertRaises(ValueError):
            client.fetch_data_assets()

    @patch("sourcing.FercCatalogClient.requests.get")
    def test_fetch_data_assets_sends_key(self, mock_get: MagicMock) -> None:
        """The catalog request sends the API key and returns asset objects."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"data-assets": [{"title": "Annual Charges"}]}
        mock_get.return_value = response

        assets = FercCatalogClient(api_key="test-key").fetch_data_assets()

        self.assertEqual(assets, [{"title": "Annual Charges"}])
        kwargs = mock_get.call_args.kwargs
        self.assertEqual(kwargs["headers"]["X-Api-Key"], "test-key")
        self.assertIn("data-assets", mock_get.call_args.args[0])

    @patch("sourcing.FercCatalogClient.requests.get")
    def test_rate_limit_raises_runtime_error(self, mock_get: MagicMock) -> None:
        """HTTP 429 becomes a RuntimeError."""
        response = MagicMock()
        response.status_code = 429
        response.text = "Too Many Requests"
        mock_get.return_value = response

        with self.assertRaises(RuntimeError) as ctx:
            FercCatalogClient(api_key="k").fetch_data_assets()
        self.assertIn("429", str(ctx.exception))

    @patch("sourcing.FercCatalogClient.requests.get")
    def test_missing_assets_list_raises(self, mock_get: MagicMock) -> None:
        """A JSON object without data-assets is an error."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"ok": True}
        mock_get.return_value = response

        with self.assertRaises(RuntimeError):
            FercCatalogClient(api_key="k").fetch_data_assets()


if __name__ == "__main__":
    unittest.main()
