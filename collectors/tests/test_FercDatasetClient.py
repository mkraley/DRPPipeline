"""Tests for FercDatasetClient."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from collectors.FercDatasetClient import FercDatasetClient
from sourcing.FercApi import FercNotFound


class TestFercDatasetClient(unittest.TestCase):
    """Tests for details, dictionary, and data paging requests."""

    @patch("collectors.FercDatasetClient.ferc_get_json", side_effect=FercNotFound("missing"))
    def test_missing_dictionary_returns_none(self, _mock_get: object) -> None:
        """HTTP 404 on the dictionary endpoint means there is no dictionary."""
        self.assertIsNone(FercDatasetClient(api_key="k").fetch_dictionary(30))

    @patch("collectors.FercDatasetClient.ferc_get_json")
    def test_fetch_data_page_sends_limit_and_offset(self, mock_get: object) -> None:
        """Data pages request limit and offset and keep row_data."""
        mock_get.return_value = {"row_data": [{"Name": "Igiugig"}], "has_more": True}

        page = FercDatasetClient(api_key="k").fetch_data_page(33, offset=10, limit=2)

        self.assertEqual(page["row_data"], [{"Name": "Igiugig"}])
        self.assertTrue(page["has_more"])
        url = mock_get.call_args.args[0]
        self.assertIn("/v1/dataset/33/data/", url)
        self.assertIn("limit=2", url)
        self.assertIn("offset=10", url)


if __name__ == "__main__":
    unittest.main()
