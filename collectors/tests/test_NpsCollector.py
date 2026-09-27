"""Tests for NpsCollector orchestration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.NpsCollector import NpsCollector
from collectors.NpsDownloadPlan import NpsPlannedFile, planned_file_dest
from utils.Args import Args
from utils.Logger import Logger
from utils.file_utils import output_folder_name

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
        store.get_project_by_drpid.return_value = {
            "breadcrumb": (
                "Collection 9688: IMD Programs > Program 2310251: APHN > "
                "Project 2306437: Mammal Inventory"
            ),
        }
        downloader = MagicMock()

        def _fake_download(
            _drpid: int, folder_path: Path, files: list[NpsPlannedFile]
        ) -> tuple:
            if not files:
                return [], False, 0, set()
            for entry in files:
                dest = planned_file_dest(folder_path, entry.relative_dir, entry.filename)
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
        project_meta = json.loads(
            (folder / "project_metadata.json").read_text(encoding="utf-8")
        )
        product_meta = json.loads(
            (folder / files[0].relative_dir / "product_metadata.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            project_meta["breadcrumb"],
            (
                "Collection 9688: IMD Programs > Program 2310251: APHN > "
                "Project 2306437: Mammal Inventory"
            ),
        )
        self.assertIn("Product 663485: Mammal inventory", product_meta["breadcrumb"])
        self.assertTrue(
            product_meta["breadcrumb"].startswith(project_meta["breadcrumb"] + " > ")
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
        self.assertEqual(result["num_files"], 3)
        store.update_public_file_count.assert_called_once_with(2, 3)

    @patch("collectors.NpsCollector.write_sidecars_for_files", return_value=[])
    def test_collect_downloads_one_product_at_a_time(
        self,
        _mock_sidecars: MagicMock,
    ) -> None:
        """Each Product is downloaded before the next Product profile is fetched."""
        collector, client, store, downloader = self._collector()
        second = dict(_PRODUCT_PROFILE)
        second["referenceId"] = 663486
        second["filesAndLinks"] = [
            {
                "fileId": 147165,
                "resourceType": "Digital File",
                "url": "https://irma.nps.gov/DataStore/DownloadFile/147165",
                "fileName": "table.csv",
            }
        ]
        client.fetch_profile.side_effect = lambda rid: {
            2306437: _PROJECT_PROFILE,
            663485: _PRODUCT_PROFILE,
            663486: second,
        }[rid]
        store.list_products_for_drpid.return_value = [
            {"irma_product_id": 663485, "title": "Mammal inventory"},
            {"irma_product_id": 663486, "title": "Mammal tables"},
        ]
        fetch_order: list[int] = []

        def _download(drpid: int, folder_path: Path, files: list[NpsPlannedFile]) -> tuple:
            fetch_order.append(int(client.fetch_profile.call_args.args[0]))
            for entry in files:
                dest = planned_file_dest(folder_path, entry.relative_dir, entry.filename)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(b"data")
            return [], False, 4, {"pdf"}

        downloader.download_files.side_effect = _download
        collector._collect(_PROJECT_URL, 2, {"title": "Mammal Inventory"})
        self.assertEqual(downloader.download_files.call_count, 2)
        self.assertEqual(fetch_order, [663485, 663486])
        first_files: list[NpsPlannedFile] = downloader.download_files.call_args_list[0].args[2]
        second_files: list[NpsPlannedFile] = downloader.download_files.call_args_list[1].args[2]
        self.assertEqual(first_files[0].filename, "report.pdf")
        self.assertEqual(second_files[0].filename, "table.csv")

    @patch("collectors.NpsCollector.write_sidecars_for_files", return_value=[])
    @patch("collectors.NpsCollector.Logger")
    def test_collect_logs_each_product(
        self,
        mock_logger: MagicMock,
        _mock_sidecars: MagicMock,
    ) -> None:
        """Product-by-product collection is logged before each download."""
        collector, _client, _store, _downloader = self._collector()
        collector._collect(_PROJECT_URL, 2, {"title": "Mammal Inventory"})
        messages = [
            call.args[0] % call.args[1:] for call in mock_logger.info.call_args_list
        ]
        self.assertTrue(any("collecting IRMA Project" in message for message in messages))
        self.assertTrue(any("fetching project profile" in message for message in messages))
        self.assertTrue(any("product 1/1" in message for message in messages))
        self.assertTrue(any("fetching product profile" in message for message in messages))
        self.assertTrue(any("file(s) in" in message for message in messages))

    @patch("collectors.NpsCollector.write_sidecars_for_files", return_value=[])
    def test_collect_skips_duplicate_same_name_and_size(
        self,
        _mock_sidecars: MagicMock,
    ) -> None:
        """Two holdings of the same PDF are downloaded once."""
        collector, client, _store, downloader = self._collector()
        client.fetch_profile.side_effect = lambda rid: {
            2306437: _PROJECT_PROFILE,
            663485: {
                **_PRODUCT_PROFILE,
                "filesAndLinks": [
                    {
                        "fileId": 420690,
                        "resourceType": "Digital File",
                        "url": "https://irma.nps.gov/DataStore/DownloadFile/420690",
                        "fileName": "WRST_Vasc_Flora_Inv_2007lowres.pdf",
                    },
                    {
                        "fileId": 450286,
                        "resourceType": "Digital File",
                        "url": "https://irma.nps.gov/DataStore/DownloadFile/450286",
                        "fileName": "WRST_Vasc_Flora_Inv_2007lowres.pdf",
                    },
                ],
            },
        }[rid]
        client.fetch_holdings.return_value = [
            {
                "Id": 420690,
                "Url": "https://irma.nps.gov/DataStore/DownloadFile/420690",
                "FileDescription": "WRST_Vasc_Flora_Inv_2007lowres.pdf",
                "FileSize": 71915109,
                "DataTableCount": 0,
            },
            {
                "Id": 450286,
                "Url": "https://irma.nps.gov/DataStore/DownloadFile/450286",
                "FileDescription": "WRST_Vasc_Flora_Inv_2007lowres.pdf",
                "FileSize": 71915109,
                "DataTableCount": 0,
            },
        ]
        collector._collect(_PROJECT_URL, 2, {"title": "Mammal Inventory"})
        product_files: list[NpsPlannedFile] = downloader.download_files.call_args.args[2]
        self.assertEqual(len(product_files), 1)
        self.assertEqual(product_files[0].filename, "WRST_Vasc_Flora_Inv_2007lowres.pdf")

    @patch("collectors.NpsCollector.write_sidecars_for_files", return_value=[])
    def test_collect_puts_project_level_files_at_root(
        self,
        _mock_sidecars: MagicMock,
    ) -> None:
        """IRMA Project Digital Files land in the NPS folder, not _project_files."""
        collector, client, _store, downloader = self._collector()
        project = dict(_PROJECT_PROFILE)
        project["filesAndLinks"] = [
            {
                "fileId": 99,
                "resourceType": "Digital File",
                "url": "https://irma.nps.gov/DataStore/DownloadFile/99",
                "fileName": "project_notes.pdf",
            }
        ]
        client.fetch_profile.side_effect = lambda rid: {
            2306437: project,
            663485: _PRODUCT_PROFILE,
        }[rid]
        result = collector._collect(
            _PROJECT_URL, 2, {"title": "Mammal Inventory", "collection_notes": ""}
        )
        folder = Path(result["folder_path"])
        project_batch: list[NpsPlannedFile] = downloader.download_files.call_args_list[0].args[2]
        self.assertEqual(project_batch[0].relative_dir, "")
        self.assertEqual(project_batch[0].filename, "project_notes.pdf")
        self.assertTrue((folder / "project_notes.pdf").is_file())
        self.assertFalse((folder / "_project_files").exists())
        self.assertTrue((folder / "project_metadata.json").is_file())

    @patch("collectors.NpsCollector.write_sidecars_for_files", return_value=[])
    def test_collect_flattens_legacy_project_files(
        self,
        _mock_sidecars: MagicMock,
    ) -> None:
        """A leftover _project_files folder is emptied into the NPS folder root."""
        collector, _client, _store, _downloader = self._collector()
        folder = self.temp_dir / output_folder_name(2)
        legacy = folder / "_project_files"
        legacy.mkdir(parents=True)
        (legacy / "old_notes.pdf").write_bytes(b"%PDF")
        collector._collect(_PROJECT_URL, 2, {"title": "Mammal Inventory"})
        self.assertTrue((folder / "old_notes.pdf").is_file())
        self.assertFalse(legacy.exists())

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
