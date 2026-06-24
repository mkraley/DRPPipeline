"""Tests for DryadApiClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sourcing.DryadApiClient import DryadApiClient

DATASET_PAYLOAD = {
    "_links": {"stash:versions": {"href": "/api/v2/datasets/doi%3Ax/versions"}},
}
VERSIONS_PAYLOAD = {
    "_embedded": {
        "stash:versions": [
            {"_links": {"stash:files": {"href": "/api/v2/versions/1/files"}}},
        ],
    },
}
FILES_PAYLOAD = {
    "_embedded": {
        "stash:files": [
            {
                "path": "data.csv",
                "size": 1024,
                "_links": {"stash:download": {"href": "/api/v2/files/9/download"}},
            },
        ],
    },
}


class TestDryadApiClient:
    """Tests for Dryad file listing."""

    @patch("sourcing.DryadApiClient.requests.get")
    def test_list_files_for_doi(self, mock_get: MagicMock) -> None:
        """Dryad DOI resolves to normalized file rows."""
        responses = [
            MagicMock(**{"json.return_value": DATASET_PAYLOAD, "raise_for_status.return_value": None}),
            MagicMock(**{"json.return_value": VERSIONS_PAYLOAD, "raise_for_status.return_value": None}),
            MagicMock(**{"json.return_value": FILES_PAYLOAD, "raise_for_status.return_value": None}),
        ]
        mock_get.side_effect = responses

        files = DryadApiClient().list_files_for_doi("10.5061/dryad.example")
        assert len(files) == 1
        assert files[0]["name"] == "data.csv"
        assert files[0]["size_bytes"] == 1024
        assert files[0]["url"].endswith("/api/v2/files/9/download")
        assert files[0]["source"] == "dryad"
