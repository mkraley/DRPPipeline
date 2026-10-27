"""Tests for Data.gov HTML / ArcGIS resource saving."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.DataGovFileDownloader import DataGovFileDownloader
from collectors.DataGovMetadataExtractor import DataGovDownloadFile
from utils.Logger import Logger


class TestDataGovFileDownloaderHtmlResources(unittest.TestCase):
    """Tests for ArcGIS hub PDF printing and FeatureServer JSON saves."""

    def setUp(self) -> None:
        """Initialize logging used by save helpers."""
        Logger.initialize(log_level="WARNING")
        self.folder = Path(__file__).parent / "_tmp_datagov_html_resources"
        self.folder.mkdir(exist_ok=True)
        self.downloader = DataGovFileDownloader()

    def tearDown(self) -> None:
        """Remove temp output folder."""
        shutil.rmtree(self.folder, ignore_errors=True)

    def test_prints_arcgis_hub_and_item_pages_with_spa_ready(self) -> None:
        """Hub/item pages use SPA-aware titled PDF rendering."""
        page_downloader = MagicMock()
        def _titled_pdf(
            url: str,
            dest_dir: Path,
            fallback_stem: str = "page",
            spa_ready: bool = False,
        ) -> Path:
            dest = dest_dir / f"{fallback_stem}.pdf"
            dest.write_bytes(b"%PDF")
            return dest

        page_downloader.url_to_titled_pdf.side_effect = _titled_pdf
        notes = self.downloader.save_html_resource_pdfs(
            2,
            page_downloader,
            self.folder,
            [
                DataGovDownloadFile(
                    label="Hub",
                    url=(
                        "https://edg-epa.hub.arcgis.com/datasets/"
                        "3c8a335f4b5243a188fd75472459e567/about"
                    ),
                    filename="about",
                ),
                DataGovDownloadFile(
                    label="Item",
                    url=(
                        "https://epa.maps.arcgis.com/home/item.html"
                        "?id=3c8a335f4b5243a188fd75472459e567"
                    ),
                    filename="item.html",
                ),
            ],
        )
        self.assertEqual(notes, [])
        self.assertEqual(page_downloader.url_to_titled_pdf.call_count, 2)
        for call in page_downloader.url_to_titled_pdf.call_args_list:
            self.assertTrue(call.kwargs.get("spa_ready"))

    @patch("collectors.DataGovFileDownloader.requests.get")
    def test_saves_feature_server_json(self, mock_get: MagicMock) -> None:
        """MapServer/FeatureServer resources are stored as JSON, not PDF."""
        response = MagicMock()
        response.status_code = 200
        response.content = b'{"fullExtent":{"xmin":1}}'
        mock_get.return_value = response
        page_downloader = MagicMock()
        notes = self.downloader.save_html_resource_pdfs(
            2,
            page_downloader,
            self.folder,
            [
                DataGovDownloadFile(
                    label="Feature service",
                    url=(
                        "https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/"
                        "services/FRS_INTERESTS_TSCA/FeatureServer"
                    ),
                    filename="FeatureServer",
                )
            ],
        )
        self.assertEqual(notes, [])
        page_downloader.url_to_titled_pdf.assert_not_called()
        written = list(self.folder.glob("*.json"))
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0].read_bytes(), b'{"fullExtent":{"xmin":1}}')
        self.assertIn("f=json", mock_get.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
