"""Tests for NpsCatalogClient HTTP helpers."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.NpsCatalogClient import (
    COLLECTION_GET_URL,
    COLLECTION_REFS_URL,
    PROFILE_URL,
    NpsCatalogClient,
)
from utils.Args import Args


class TestNpsCatalogClient(unittest.TestCase):
    """Tests for IRMA Collection and Profile requests."""

    def setUp(self) -> None:
        """Initialize Args for client construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "nps_catalog_client"]
        Args.initialize()

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("sourcing.NpsCatalogClient.requests.get")
    def test_fetch_profile_gets_v8_url(self, mock_get: MagicMock) -> None:
        """Profile requests use the v8 REST URL."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"referenceId": 2310251}
        mock_get.return_value = response

        payload = NpsCatalogClient(timeout_sec=10).fetch_profile(2310251)

        self.assertEqual(payload["referenceId"], 2310251)
        mock_get.assert_called_once()
        self.assertEqual(mock_get.call_args.args[0], PROFILE_URL.format(2310251))

    @patch("sourcing.NpsCatalogClient.requests.get")
    def test_fetch_collection_gets_by_id(self, mock_get: MagicMock) -> None:
        """Collection metadata uses GetById."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"Id": 9688, "Title": "IMD Programs"}
        mock_get.return_value = response

        payload = NpsCatalogClient().fetch_collection(9688)

        self.assertEqual(payload["Title"], "IMD Programs")
        self.assertEqual(mock_get.call_args.args[0], COLLECTION_GET_URL.format(9688))

    @patch("sourcing.NpsCatalogClient.requests.post")
    def test_fetch_collection_programs_posts_form(self, mock_post: MagicMock) -> None:
        """Program members are posted as collectionId form data."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = [{"Id": 2310251, "Title": "APHN"}]
        mock_post.return_value = response

        rows = NpsCatalogClient().fetch_collection_programs(9688)

        self.assertEqual(rows[0]["Id"], 2310251)
        self.assertEqual(mock_post.call_args.args[0], COLLECTION_REFS_URL)
        self.assertEqual(mock_post.call_args.kwargs["data"], {"collectionId": 9688})

    @patch("sourcing.NpsCatalogClient.requests.get")
    def test_http_error_raises_runtime_error(self, mock_get: MagicMock) -> None:
        """Non-success HTTP status becomes RuntimeError."""
        response = MagicMock()
        response.status_code = 500
        response.text = "boom"
        mock_get.return_value = response

        with self.assertRaises(RuntimeError) as ctx:
            NpsCatalogClient().fetch_profile(1)
        self.assertIn("500", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
