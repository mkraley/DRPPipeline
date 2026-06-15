"""Tests for UsfsCollector download size policy."""

import sys
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.UsfsCollector import (
    MAX_DOWNLOAD_BYTES,
    STATUS_COLLECTED_EXTERNAL_ARCHIVE,
    STATUS_COLLECTED_LARGE_FILE,
    UsfsCollector,
    _PDF_NAMES,
)


class TestUsfsCollector(unittest.TestCase):
    def setUp(self) -> None:
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        sys.argv = self._original_argv

    @patch("collectors.UsfsCollector.download_via_url")
    def test_skips_download_over_1gb(self, mock_download: MagicMock) -> None:
        catalog_bytes = MAX_DOWNLOAD_BYTES + 1
        collector = UsfsCollector()
        folder = Path(__file__).parent / "_tmp_usfs_test"
        folder.mkdir(exist_ok=True)
        try:
            notes, total_bytes, exts, skipped_large = collector._process_publication_files(
                1,
                MagicMock(),
                folder,
                [("big.zip", "https://example.com/big.zip", catalog_bytes)],
            )
            mock_download.assert_not_called()
            self.assertEqual(total_bytes, catalog_bytes)
            self.assertTrue(skipped_large)
            self.assertTrue(any("Skipped download (>1GB)" in n for n in notes))
            self.assertIn("zip", exts)
        finally:
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()

    def test_pdf_names_constant(self) -> None:
        self.assertEqual(len(_PDF_NAMES), 3)

    @patch("collectors.UsfsCollector.record_error")
    @patch("collectors.UsfsCollector.download_via_url", return_value=(0, False))
    def test_download_failure_records_error(
        self, mock_http_download: MagicMock, mock_record_error: MagicMock
    ) -> None:
        collector = UsfsCollector()
        folder = Path(__file__).parent / "_tmp_usfs_dl_fail"
        folder.mkdir(exist_ok=True)
        page_downloader = MagicMock()
        page_downloader.download_file.return_value = (0, False)
        try:
            notes, total_bytes, _exts, skipped_large = collector._process_publication_files(
                1,
                page_downloader,
                folder,
                [(
                    "meta.zip",
                    "https://www.fs.usda.gov/rds/archive/products/RDS/meta.zip",
                    1024,
                )],
            )
            page_downloader.download_file.assert_called_once()
            mock_http_download.assert_called_once()
            mock_record_error.assert_called_once()
            self.assertIn("Download failed", mock_record_error.call_args[0][1])
            self.assertFalse(skipped_large)
            self.assertTrue(any("Download failed" in n for n in notes))
            self.assertEqual(total_bytes, 0)
        finally:
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.UsfsCollector.Logger")
    @patch("collectors.UsfsCollector.download_via_url")
    def test_download_usfs_logs_begin_and_end(
        self, mock_http_download: MagicMock, mock_logger: MagicMock
    ) -> None:
        collector = UsfsCollector()
        folder = Path(__file__).parent / "_tmp_usfs_dl_log"
        folder.mkdir(exist_ok=True)
        page_downloader = MagicMock()

        def _write_download(_url: str, dest_path: Path) -> tuple[int, bool]:
            dest_path.write_bytes(b"x" * 128)
            return 128, True

        page_downloader.download_file.side_effect = _write_download
        try:
            collector._process_publication_files(
                1,
                page_downloader,
                folder,
                [(
                    "meta.zip",
                    "https://www.fs.usda.gov/rds/archive/products/RDS/meta.zip",
                    128,
                )],
            )
            mock_logger.info.assert_any_call(
                "Downloading publication file: %s (%s)",
                "meta.zip",
                mock.ANY,
            )
            mock_logger.info.assert_any_call("Downloaded publication file: %s", "meta.zip")
        finally:
            for f in folder.glob("*"):
                f.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.UsfsCollector.download_via_url")
    def test_download_usfs_uses_playwright_first(self, mock_http_download: MagicMock) -> None:
        collector = UsfsCollector()
        folder = Path(__file__).parent / "_tmp_usfs_dl_pw"
        folder.mkdir(exist_ok=True)
        page_downloader = MagicMock()
        page_downloader.download_file.return_value = (128, True)
        try:
            notes, total_bytes, _exts, skipped_large = collector._process_publication_files(
                1,
                page_downloader,
                folder,
                [(
                    "meta.zip",
                    "https://www.fs.usda.gov/rds/archive/products/RDS/meta.zip",
                    128,
                )],
            )
            page_downloader.download_file.assert_called_once()
            mock_http_download.assert_not_called()
            self.assertFalse(skipped_large)
            self.assertEqual(total_bytes, 128)
            self.assertFalse(any("Download failed" in n for n in notes))
        finally:
            for f in folder.glob("*"):
                f.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.UsfsCollector.Storage")
    def test_update_storage_excludes_metadata_parse_fields(self, mock_storage: MagicMock) -> None:
        mock_storage.get.return_value = {"status": "sourced", "errors": None}
        collector = UsfsCollector()
        result = {
            "folder_path": "C:\\data\\DRP000001",
            "geographic_coverage": "Oregon",
            "geographic_extent_description": "NW Oregon",
            "place_keywords": ["Oregon"],
            "bounding_box": {"west": -125.0, "east": -124.0, "north": 46.0, "south": 45.0},
        }
        collector._update_storage(1, result)
        update = mock_storage.update_record.call_args[0][1]
        self.assertEqual(update["geographic_coverage"], "Oregon")
        self.assertNotIn("geographic_extent_description", update)
        self.assertNotIn("place_keywords", update)
        self.assertNotIn("bounding_box", update)

    @patch("collectors.UsfsCollector.Storage")
    def test_update_storage_large_file_status(self, mock_storage: MagicMock) -> None:
        mock_storage.get.return_value = {"status": "sourced", "errors": None}
        collector = UsfsCollector()
        result = {"folder_path": "C:\\data\\DRP000001", "_skipped_large_file": True}
        collector._update_storage(1, result)
        mock_storage.update_record.assert_called_once()
        update = mock_storage.update_record.call_args[0][1]
        self.assertEqual(update["status"], STATUS_COLLECTED_LARGE_FILE)
        self.assertNotIn("_skipped_large_file", update)

    @patch("collectors.UsfsCollector.Storage")
    def test_update_storage_external_archive_status(self, mock_storage: MagicMock) -> None:
        mock_storage.get.return_value = {"status": "sourced", "errors": None}
        collector = UsfsCollector()
        result = {"folder_path": "C:\\data\\DRP000001", "_external_archive": True}
        collector._update_storage(1, result)
        mock_storage.update_record.assert_called_once()
        update = mock_storage.update_record.call_args[0][1]
        self.assertEqual(update["status"], STATUS_COLLECTED_EXTERNAL_ARCHIVE)
        self.assertNotIn("_external_archive", update)

    @patch("collectors.UsfsCollector.Storage")
    def test_update_storage_preserves_error_status(self, mock_storage: MagicMock) -> None:
        mock_storage.get.return_value = {"status": "sourced-error", "errors": "Download failed"}
        collector = UsfsCollector()
        result = {"folder_path": "C:\\data\\DRP000001", "_skipped_large_file": True}
        collector._update_storage(1, result)
        update = mock_storage.update_record.call_args[0][1]
        self.assertNotIn("status", update)
        self.assertNotIn("_skipped_large_file", update)

    @patch("collectors.UsfsCollector.record_warning")
    @patch("collectors.UsfsAria2Export.write_drpid_aria2_cmd")
    @patch("collectors.UsfsCollector.create_output_folder")
    @patch("collectors.UsfsCollector._fetch_usfs_page_body")
    @patch("collectors.UsfsCollector.Storage")
    def test_collect_external_archive_sets_status_and_warning(
        self,
        mock_storage: MagicMock,
        mock_fetch: MagicMock,
        mock_create_folder: MagicMock,
        mock_write_cmd: MagicMock,
        mock_record_warning: MagicMock,
    ) -> None:
        mock_storage.get.return_value = {
            "source_url": "https://www.fs.usda.gov/rds/archive/catalog/RDS-ext-2024-0001",
        }
        folder = Path(__file__).parent / "_tmp_usfs_ext_archive"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        detail_html = "<html><head><title>T</title></head><body><h1>T</h1></body></html>"
        mock_fetch.return_value = (200, detail_html, "text/html", False)
        external_url = "https://doi.org/10.60594/W4WC78"

        collector = UsfsCollector()
        page_downloader = MagicMock()
        with patch.object(collector, "_save_page_pdfs"), patch(
            "collectors.UsfsCollector.parse_data_access_links",
            return_value={
                "publication_files": [],
                "metadata_url": "https://www.fs.usda.gov/rds/meta.html",
                "fileindex_url": "",
                "external_archive_url": external_url,
            },
        ), patch(
            "collectors.UsfsCollector.parse_detail_page",
            return_value={"title": "T"},
        ), patch(
            "collectors.UsfsCollector.rds_id_from_source_url",
            return_value="RDS-ext-2024-0001",
        ), patch(
            "collectors.UsfsCollector.merge_usfs_metadata",
            return_value={"title": "T"},
        ), patch(
            "collectors.UsfsCollector.infer_data_types",
            return_value="",
        ), patch(
            "collectors.UsfsCollector.normalize_geographic_metadata",
        ) as mock_geo:
            mock_geo.return_value.geographic_coverage = ""
            mock_geo.return_value.warnings = []
            result = collector._collect(
                "https://www.fs.usda.gov/rds/archive/catalog/RDS-ext-2024-0001",
                177,
                page_downloader,
            )

        mock_write_cmd.assert_not_called()
        mock_record_warning.assert_any_call(
            177,
            f"Data available via external archive (not downloaded): {external_url}",
        )
        self.assertTrue(result["_external_archive"])
        self.assertIn("External archive (not downloaded)", result["status_notes"])
        self.assertIn(external_url, result["status_notes"])
        self.assertEqual(result["num_files"], 3)
        try:
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            pass

    @patch("collectors.UsfsAria2Export.write_drpid_aria2_cmd")
    @patch("collectors.UsfsCollector.create_output_folder")
    @patch("collectors.UsfsCollector._fetch_usfs_page_body")
    @patch("collectors.UsfsCollector.Storage")
    def test_collect_writes_aria2_cmd_when_large_file_skipped(
        self,
        mock_storage: MagicMock,
        mock_fetch: MagicMock,
        mock_create_folder: MagicMock,
        mock_write_cmd: MagicMock,
    ) -> None:
        mock_storage.get.return_value = {"source_url": "https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0001"}
        folder = Path(__file__).parent / "_tmp_usfs_aria2_collect"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        mock_write_cmd.return_value = folder.parent / "DRP000001.cmd"
        big = MAX_DOWNLOAD_BYTES + 1
        detail_html = "<html><head><title>T</title></head><body><h1>T</h1></body></html>"
        mock_fetch.return_value = (200, detail_html, "text/html", False)

        collector = UsfsCollector()
        page_downloader = MagicMock()
        with patch.object(
            collector,
            "_save_page_pdfs",
        ), patch(
            "collectors.UsfsCollector.parse_data_access_links",
            return_value={
                "publication_files": [("big.zip", "https://example.com/big.zip", big)],
                "metadata_url": "",
                "fileindex_url": "",
            },
        ), patch(
            "collectors.UsfsCollector.parse_detail_page",
            return_value={"title": "T"},
        ), patch(
            "collectors.UsfsCollector.rds_id_from_source_url",
            return_value=None,
        ), patch(
            "collectors.UsfsCollector.merge_usfs_metadata",
            return_value={"title": "T"},
        ), patch(
            "collectors.UsfsCollector.infer_data_types",
            return_value="",
        ), patch(
            "collectors.UsfsCollector.normalize_geographic_metadata",
        ) as mock_geo:
            mock_geo.return_value.geographic_coverage = ""
            mock_geo.return_value.warnings = []
            collector._collect(
                "https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0001",
                1,
                page_downloader,
            )

        mock_write_cmd.assert_called_once()
        try:
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            pass

    @patch("collectors.UsfsCollector.create_output_folder")
    @patch("collectors.UsfsCollector.Storage")
    def test_resolve_collection_folder_metadata_only_uses_stored_path(
        self,
        mock_storage: MagicMock,
        mock_create_folder: MagicMock,
    ) -> None:
        folder = Path(__file__).parent / "_tmp_usfs_meta_only_path"
        folder.mkdir(exist_ok=True)
        try:
            mock_storage.get.return_value = {"folder_path": str(folder)}
            collector = UsfsCollector()
            path = collector._resolve_collection_folder(1, metadata_only=True)
            self.assertEqual(path, folder)
            mock_create_folder.assert_not_called()
        finally:
            folder.rmdir()

    @patch("collectors.UsfsCollector.create_output_folder")
    @patch("collectors.UsfsCollector.Storage")
    def test_resolve_collection_folder_metadata_only_creates_without_recreate(
        self,
        mock_storage: MagicMock,
        mock_create_folder: MagicMock,
    ) -> None:
        folder = Path(__file__).parent / "_tmp_usfs_meta_only_new"
        mock_create_folder.return_value = folder
        mock_storage.get.return_value = {}
        collector = UsfsCollector()
        path = collector._resolve_collection_folder(5, metadata_only=True)
        self.assertEqual(path, folder)
        mock_create_folder.assert_called_once()
        args, kwargs = mock_create_folder.call_args
        self.assertEqual(args[1], 5)
        self.assertFalse(kwargs.get("recreate", True))

    @patch("collectors.UsfsCollector._fetch_usfs_page_body")
    @patch("collectors.UsfsCollector.Storage")
    def test_collect_metadata_only_skips_publication_downloads(
        self,
        mock_storage: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        folder = Path(__file__).parent / "_tmp_usfs_meta_only_collect"
        folder.mkdir(exist_ok=True)
        marker = folder / "keep.dat"
        marker.write_bytes(b"stay")
        Args._config["usfs_metadata_only"] = True
        mock_storage.get.return_value = {
            "source_url": "https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0001",
            "folder_path": str(folder),
        }
        detail_html = "<html><head><title>T</title></head><body><h1>T</h1></body></html>"
        mock_fetch.return_value = (200, detail_html, "text/html", False)

        collector = UsfsCollector()
        page_downloader = MagicMock()
        with patch.object(collector, "_save_page_pdfs"), patch.object(
            collector,
            "_process_publication_files",
            return_value=([], 0, set(), False),
        ) as mock_process, patch(
            "collectors.UsfsCollector.parse_data_access_links",
            return_value={
                "publication_files": [("data.zip", "https://example.com/data.zip", 1024)],
                "metadata_url": "",
                "fileindex_url": "",
                "external_archive_url": "",
            },
        ), patch(
            "collectors.UsfsCollector.parse_detail_page",
            return_value={"title": "T"},
        ), patch(
            "collectors.UsfsCollector.rds_id_from_source_url",
            return_value=None,
        ), patch(
            "collectors.UsfsCollector.merge_usfs_metadata",
            return_value={"title": "T"},
        ), patch(
            "collectors.UsfsCollector.infer_data_types",
            return_value="",
        ), patch(
            "collectors.UsfsCollector.normalize_geographic_metadata",
        ) as mock_geo:
            mock_geo.return_value.geographic_coverage = ""
            mock_geo.return_value.warnings = []
            collector._collect(
                "https://www.fs.usda.gov/rds/archive/catalog/RDS-2020-0001",
                1,
                page_downloader,
            )

        mock_process.assert_called_once()
        self.assertFalse(mock_process.call_args.kwargs.get("download", True))
        page_downloader.download_file.assert_not_called()
        self.assertTrue(marker.exists())
        Args._config["usfs_metadata_only"] = False
        try:
            marker.unlink(missing_ok=True)
            folder.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    unittest.main()
