"""Tests for EpaHubCatalogClient."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.EpaHubCatalogClient import DEFAULT_ITEMS_URL, EpaHubCatalogClient
from utils.Args import Args

_ITEM = "a" * 32


def _response(payload: dict) -> MagicMock:
    """Return a mock HTTP response with the given JSON body."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


class TestEpaHubCatalogClient(unittest.TestCase):
    """Tests for Clip and Ship catalog paging."""

    def setUp(self) -> None:
        """Initialize Args so the default items URL can be resolved."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "epa_hub_catalog"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_page_size_must_be_positive(self) -> None:
        """page_size below 1 is rejected."""
        with self.assertRaises(ValueError):
            EpaHubCatalogClient(items_url=DEFAULT_ITEMS_URL, page_size=0)

    @patch("sourcing.EpaHubCatalogClient.requests.get")
    def test_fetch_items_follows_number_matched(self, mock_get: MagicMock) -> None:
        """A short first page is followed until numberMatched is covered."""
        mock_get.side_effect = [
            _response(
                {
                    "numberMatched": 2,
                    "features": [{"id": _ITEM, "properties": {"title": "One"}}],
                }
            ),
            _response(
                {
                    "numberMatched": 2,
                    "features": [{"id": "b" * 32, "properties": {"title": "Two"}}],
                }
            ),
        ]
        items = EpaHubCatalogClient(items_url=DEFAULT_ITEMS_URL, page_size=100).fetch_items()
        self.assertEqual([item["id"] for item in items], [_ITEM, "b" * 32])
        second_params = mock_get.call_args_list[1].kwargs["params"]
        self.assertEqual(second_params["startindex"], 2)
        self.assertEqual(mock_get.call_args_list[0].args[0], DEFAULT_ITEMS_URL)

    @patch("sourcing.EpaHubCatalogClient.requests.get")
    def test_rate_limit_raises_runtime_error(self, mock_get: MagicMock) -> None:
        """HTTP 429 becomes a RuntimeError."""
        response = MagicMock()
        response.status_code = 429
        response.text = "Too Many Requests"
        mock_get.return_value = response
        with self.assertRaises(RuntimeError) as ctx:
            EpaHubCatalogClient(items_url=DEFAULT_ITEMS_URL).fetch_page(1)
        self.assertIn("429", str(ctx.exception))

    @patch("sourcing.EpaHubCatalogClient.requests.get")
    def test_missing_features_raises(self, mock_get: MagicMock) -> None:
        """A JSON object without features is an error."""
        mock_get.return_value = _response({"numberMatched": 0})
        with self.assertRaises(RuntimeError):
            EpaHubCatalogClient(items_url=DEFAULT_ITEMS_URL).fetch_items()


if __name__ == "__main__":
    unittest.main()
