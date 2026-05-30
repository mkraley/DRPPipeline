"""Tests for UsfsCollector download size policy."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.UsfsCollector import (
    MAX_DOWNLOAD_BYTES,
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
        self, _mock_download: MagicMock, mock_record_error: MagicMock
    ) -> None:
        collector = UsfsCollector()
        folder = Path(__file__).parent / "_tmp_usfs_dl_fail"
        folder.mkdir(exist_ok=True)
        try:
            notes, total_bytes, _exts, skipped_large = collector._process_publication_files(
                1,
                MagicMock(),
                folder,
                [("meta.zip", "https://example.com/meta.zip", 1024)],
            )
            mock_record_error.assert_called_once()
            self.assertIn("Download failed", mock_record_error.call_args[0][1])
            self.assertFalse(skipped_large)
            self.assertTrue(any("Download failed" in n for n in notes))
            self.assertEqual(total_bytes, 0)
        finally:
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()

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
    def test_update_storage_preserves_error_status(self, mock_storage: MagicMock) -> None:
        mock_storage.get.return_value = {"status": "sourced-error", "errors": "Download failed"}
        collector = UsfsCollector()
        result = {"folder_path": "C:\\data\\DRP000001", "_skipped_large_file": False}
        collector._update_storage(1, result)
        update = mock_storage.update_record.call_args[0][1]
        self.assertNotIn("status", update)

    @patch("collectors.UsfsAria2Export.write_drpid_aria2_cmd")
    @patch("collectors.UsfsCollector.create_output_folder")
    @patch("collectors.UsfsCollector.fetch_page_body")
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


if __name__ == "__main__":
    unittest.main()
