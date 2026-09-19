"""Tests for NpsCollector orchestration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.NpsCollector import NpsCollector
from collectors.NpsDownloadPlan import NpsPlannedFile
from utils.Args import Args
from utils.Logger import Logger

_PROJECT_URL = "https://irma.nps.gov/DataStore/Reference/Profile/2306437"
_PROJECT_PROFILE = {
    "referenceId": 2306437,
    "visibility": "Public",
    "bibliography": {
        "title": "Mammal Inventory",
        "abstract": "<p>Park mammal surveys.</p>",
        "contentBegin": {"year": 2013, "precision": "YYYY"},
        "publisher": {"publisherName": "National Park Service"},
        "contacts": [
            {
                "contactType": "Lead(s)",
                "contacts": [{"firstName": "Pat", "primaryName": "Lead", "affiliation": "NPS"}],
            }
        ],
    },
    "filesAndLinks": [],
}
_PRODUCT_PROFILE = {
    "referenceId": 663485,
    "visibility": "Public",
    "citation": (
        "Britzke. 2007. Mammal inventory. https://doi.org/10.36967/663485"
    ),
    "bibliography": {
        "title": "Mammal inventory",
        "notes": "Protocol revision.",
        "issued": {"year": 2007, "precision": "YYYY"},
    },
    "units": [{"unitCode": "BLRI", "unitName": "Blue Ridge Parkway"}],
    "boundingBoxes": [
        {"wkt": "POLYGON ((-79.1 35.5, -78.5 35.5, -78.5 36.0, -79.1 36.0, -79.1 35.5))"}
    ],
    "filesAndLinks": [
        {
            "fileId": 147164,
            "resourceType": "Digital File",
            "url": "https://irma.nps.gov/DataStore/DownloadFile/147164",
            "fileName": "report.pdf",
        }
    ],
}


class TestNpsCollector(unittest.TestCase):
    """Tests for NPS collector folder layout and inventory fields."""

    def setUp(self) -> None:
        """Initialize Args and a temp output folder."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        Args._config["base_output_dir"] = str(self.temp_dir)

    def tearDown(self) -> None:
        """Restore argv and remove temp files."""
        sys.argv = self._original_argv
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _collector(self) -> tuple[NpsCollector, MagicMock, MagicMock, MagicMock]:
        """Build a collector with mocked IRMA, hierarchy, and downloader."""
        client = MagicMock()
        client.fetch_profile.side_effect = lambda rid: {
            2306437: _PROJECT_PROFILE,
            663485: _PRODUCT_PROFILE,
        }[rid]
        client.fetch_holdings.return_value = [
            {
                "Id": 147164,
                "Url": "https://irma.nps.gov/DataStore/DownloadFile/147164",
                "FileDescription": "report.pdf",
                "FileSize": 8,
                "DataTableCount": 0,
            }
        ]
        store = MagicMock()
        store.list_products_for_drpid.return_value = [
            {"irma_product_id": 663485, "title": "Mammal inventory"}
        ]
        downloader = MagicMock()

        def _fake_download(_drpid: int, folder_path: Path, files: list[NpsPlannedFile]) -> tuple:
            dest = folder_path / files[0].relative_dir / files[0].filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4")
            return [], False, 8, {"pdf"}

        downloader.download_files.side_effect = _fake_download
        collector = NpsCollector(
            client=client,
            hierarchy_store=store,
            file_downloader=downloader,
            request_delay=0,
        )
        return collector, client, store, downloader

    @patch("collectors.NpsCollector.write_sidecars_for_files", return_value=[])
    def test_collect_plans_product_subfolder(
        self,
        _mock_sidecars: MagicMock,
    ) -> None:
        """Public product files are planned into a title-only subfolder."""
        collector, _client, store, downloader = self._collector()
        result = collector._collect(
            _PROJECT_URL,
            2,
            {"title": "Mammal Inventory", "collection_notes": "Collection 9688: IMD"},
        )
        folder = Path(result["folder_path"])
        self.assertTrue(folder.is_dir())
        store.list_products_for_drpid.assert_called_once_with(2)
        files: list[NpsPlannedFile] = downloader.download_files.call_args.args[2]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].relative_dir, "Mammal_inventory")
        self.assertNotIn("663485", files[0].relative_dir)
        self.assertEqual(files[0].filename, "report.pdf")
        self.assertTrue((folder / files[0].relative_dir / "report.pdf").is_file())
        self.assertTrue((folder / "project_metadata.json").is_file())
        self.assertTrue((folder / files[0].relative_dir / "product_metadata.json").is_file())
        product_meta = json.loads(
            (folder / files[0].relative_dir / "product_metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(product_meta["notes"], "Protocol revision.")
        self.assertEqual(product_meta["doi"], "10.36967/663485")
        self.assertIn("North Carolina", product_meta["geographic_coverage"])
        self.assertEqual(result["agency"], "Department of the Interior")
        self.assertEqual(result["office"], "National Park Service")
        self.assertEqual(result["time_start"], "2013")
        self.assertIn("Leads", result["summary"])
        self.assertNotIn("Collection ", result["summary"])
        self.assertIn("DOI: 10.36967/663485", result["collection_notes"])
        self.assertIn("Collection 9688: IMD", result["collection_notes"])
        self.assertIn("pdf", result.get("extensions", ""))

    @patch("collectors.NpsCollector.record_error")
    def test_collect_rejects_non_irma_url(self, mock_error: MagicMock) -> None:
        """Non-IRMA URLs are rejected before any download."""
        collector, _client, _store, downloader = self._collector()
        result = collector._collect("https://example.com/x", 1, {})
        self.assertEqual(result, {})
        mock_error.assert_called()
        downloader.download_files.assert_not_called()


if __name__ == "__main__":
    unittest.main()
