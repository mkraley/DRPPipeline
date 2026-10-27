"""Tests for SsaCatalogClient thin wrapper."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from sourcing.SsaCatalogClient import SsaCatalogClient
from utils.Args import Args


class TestSsaCatalogClient(unittest.TestCase):
    """Tests for SSA defaults on the shared catalog client."""

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

    @patch("sourcing.DataGovCatalogClient.requests.get")
    def test_defaults_to_ssa_org_slug(self, mock_get: MagicMock) -> None:
        """Wrapper defaults org_slug to ssa."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": []}
        mock_get.return_value = response

        SsaCatalogClient(api_key="test-key").fetch_search_page()

        self.assertEqual(mock_get.call_args.kwargs["params"]["org_slug"], "ssa")


if __name__ == "__main__":
    unittest.main()
