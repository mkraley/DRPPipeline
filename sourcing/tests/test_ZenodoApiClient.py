"""Tests for ZenodoApiClient."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from sourcing.ZenodoApiClient import ZenodoApiClient


class TestZenodoApiClient:
    """Tests for Zenodo file listing."""

    @patch("sourcing.ZenodoApiClient.requests.get")
    def test_list_files_for_doi(self, mock_get: MagicMock) -> None:
        """Zenodo DOI resolves to normalized file rows."""
        response = MagicMock()
        response.json.return_value = {
            "files": [
                {
                    "key": "bundle.zip",
                    "size": 2048,
                    "links": {"self": "https://zenodo.org/api/records/1/files/bundle.zip/content"},
                },
            ],
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        files = ZenodoApiClient().list_files_for_doi("10.5281/zenodo.17627111")
        assert len(files) == 1
        assert files[0]["name"] == "bundle.zip"
        assert files[0]["size_bytes"] == 2048
        assert files[0]["source"] == "zenodo"

    def test_record_id_from_doi_invalid(self) -> None:
        """Non-Zenodo DOIs return no files."""
        client = ZenodoApiClient()
        assert client.list_files_for_doi("10.15482/USDA.ADC/1") == []
