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
            del url, spa_ready
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

    @patch("collectors.DataGovFileDownloader.requests.get")
    def test_falls_back_to_raw_html_when_pdf_fails(
        self, mock_get: MagicMock
    ) -> None:
        """When print-to-PDF fails, DATA_README.html is saved as raw HTML."""
        response = MagicMock()
        response.status_code = 200
        response.content = b"<!DOCTYPE html><html><body>readme</body></html>"
        mock_get.return_value = response
        page_downloader = MagicMock()
        page_downloader.url_to_titled_pdf.return_value = None
        notes = self.downloader.save_html_resource_pdfs(
            191,
            page_downloader,
            self.folder,
            [
                DataGovDownloadFile(
                    label="README",
                    url=(
                        "https://pasteur.epa.gov/uploads/10.23719/1531881/"
                        "DATA_README.html"
                    ),
                    filename="DATA_README.html",
                )
            ],
        )
        self.assertEqual(notes, [])
        page_downloader.url_to_titled_pdf.assert_called_once()
        dest = self.folder / "DATA_README.html"
        self.assertTrue(dest.is_file())
        self.assertIn(b"readme", dest.read_bytes())

    @patch("collectors.DataGovFileDownloader.record_error")
    @patch("collectors.DataGovFileDownloader.requests.get")
    def test_arcgis_json_failure_notes_partial_success(
        self,
        mock_get: MagicMock,
        mock_record_error: MagicMock,
    ) -> None:
        """Resource save failures continue and report partial resource success."""
        import requests

        mock_get.side_effect = [
            MagicMock(status_code=200, content=b'{"ok":1}'),
            requests.exceptions.ConnectionError("DNS failed"),
        ]
        page_downloader = MagicMock()
        notes = self.downloader.save_html_resource_pdfs(
            29,
            page_downloader,
            self.folder,
            [
                DataGovDownloadFile(
                    label="ok",
                    url=(
                        "https://gispub.epa.gov/arcgis/rest/services/"
                        "OEI/FRS_Wastewater/MapServer"
                    ),
                    filename="MapServer",
                ),
                DataGovDownloadFile(
                    label="bad",
                    url=(
                        "https://igeo.epa.gov/arcgis/rest/services/"
                        "OEI/FRS_ESF3/MapServer"
                    ),
                    filename="MapServer",
                ),
            ],
        )
        self.assertTrue(any("FRS_ESF3" in note for note in notes))
        mock_record_error.assert_called_once()
        message = mock_record_error.call_args[0][1]
        self.assertIn("1 of 2", message)
        self.assertIn("1 resource(s) saved", message)
        self.assertEqual(len(list(self.folder.glob("*.json"))), 1)

    @patch("collectors.DataGovFileDownloader.record_error")
    @patch("collectors.DataGovFileDownloader.requests.get")
    def test_all_html_resource_failures_note_data_downloads_continue(
        self,
        mock_get: MagicMock,
        mock_record_error: MagicMock,
    ) -> None:
        """All HTML failures still note that data downloads continue separately."""
        mock_get.return_value = MagicMock(status_code=500, content=b"")
        page_downloader = MagicMock()
        page_downloader.url_to_titled_pdf.return_value = None
        notes = self.downloader.save_html_resource_pdfs(
            29,
            page_downloader,
            self.folder,
            [
                DataGovDownloadFile(
                    label="a",
                    url="https://example.com/a.html",
                    filename="a.html",
                ),
                DataGovDownloadFile(
                    label="b",
                    url="https://example.com/b.html",
                    filename="b.html",
                ),
            ],
        )
        self.assertEqual(len(notes), 2)
        mock_record_error.assert_called_once()
        message = mock_record_error.call_args[0][1]
        self.assertIn("All 2", message)
        self.assertIn("data-file downloads continued separately", message)
        self.assertNotIn("none were successfully accessed", message)


if __name__ == "__main__":
    unittest.main()
