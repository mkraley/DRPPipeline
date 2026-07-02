"""Tests for AdcCollector download size policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.AdcCollector import (
    STATUS_COLLECTED_EXTERNAL_ARCHIVE,
    STATUS_COLLECTED_LARGE_FILE,
    AdcCollector,
)
from collectors.AdcCollector import _CATALOG_HTML_NAME, _METADATA_JSON_NAME
from sourcing.AdcFileInventory import MAX_DOWNLOAD_BYTES, AdcFileInventory
from utils.file_utils import format_file_size


class TestAdcCollector(unittest.TestCase):
    """Tests for ADC collector behavior."""

    def setUp(self) -> None:
        """Initialize Args and Logger for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("collectors.AdcCollector.download_via_url")
    def test_skips_download_over_1gb(self, mock_download: MagicMock) -> None:
        """Files over 1 GB are skipped and noted in status_notes."""
        catalog_bytes = MAX_DOWNLOAD_BYTES + 1
        collector = AdcCollector()
        folder = Path(__file__).parent / "_tmp_adc_test"
        folder.mkdir(exist_ok=True)
        try:
            notes, total_bytes, exts, skipped_large = collector._process_files(
                1,
                folder,
                [{
                    "name": "big.zip",
                    "url": "https://example.com/big.zip",
                    "size_bytes": catalog_bytes,
                    "source": "figshare",
                }],
            )
            mock_download.assert_not_called()
            self.assertEqual(total_bytes, catalog_bytes)
            self.assertTrue(skipped_large)
            self.assertTrue(any("Skipped download (>1GB)" in note for note in notes))
            self.assertIn("zip", exts)
        finally:
            for file_path in folder.iterdir():
                file_path.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.AdcCollector.download_via_url", return_value=(128, True))
    def test_downloads_small_file(self, mock_download: MagicMock) -> None:
        """Files under 1 GB are downloaded."""
        collector = AdcCollector()
        folder = Path(__file__).parent / "_tmp_adc_dl"
        folder.mkdir(exist_ok=True)

        def _write(_url: str, dest: Path, **_kwargs: object) -> tuple[int, bool]:
            dest.write_bytes(b"x" * 128)
            return 128, True

        mock_download.side_effect = _write
        try:
            notes, total_bytes, _exts, skipped_large = collector._process_files(
                1,
                folder,
                [{
                    "name": "small.csv",
                    "url": "https://example.com/small.csv",
                    "size_bytes": 128,
                    "source": "figshare",
                }],
            )
            mock_download.assert_called_once()
            self.assertEqual(total_bytes, 128)
            self.assertFalse(skipped_large)
            self.assertEqual(notes, [])
        finally:
            for file_path in folder.iterdir():
                file_path.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.AdcCollector.download_via_url")
    def test_collect_includes_skipped_large_in_file_size(
        self,
        mock_download: MagicMock,
    ) -> None:
        """Collection stats include skipped >1GB files in num_files and file_size."""
        catalog_bytes = MAX_DOWNLOAD_BYTES + 1
        small_bytes = 128
        collector = AdcCollector()
        folder = Path(__file__).parent / "_tmp_adc_summary"
        folder.mkdir(exist_ok=True)
        (folder / _METADATA_JSON_NAME).write_text("{}", encoding="utf-8")
        (folder / _CATALOG_HTML_NAME).write_text("<html></html>", encoding="utf-8")

        def _write(_url: str, dest: Path, **_kwargs: object) -> tuple[int, bool]:
            dest.write_bytes(b"x" * small_bytes)
            return small_bytes, True

        mock_download.side_effect = _write
        files = [
            {
                "name": "small.csv",
                "url": "https://example.com/small.csv",
                "size_bytes": small_bytes,
                "source": "figshare",
            },
            {
                "name": "big.zip",
                "url": "https://example.com/big.zip",
                "size_bytes": catalog_bytes,
                "source": "figshare",
            },
        ]
        try:
            notes, inventory_bytes, exts, skipped_large = collector._process_files(
                1,
                folder,
                files,
            )
            summary = collector._collection_summary(
                folder,
                files,
                inventory_bytes,
                exts,
            )
            self.assertTrue(skipped_large)
            self.assertEqual(summary["num_files"], 4)
            expected_bytes = small_bytes + catalog_bytes
            expected_bytes += (folder / _METADATA_JSON_NAME).stat().st_size
            expected_bytes += (folder / _CATALOG_HTML_NAME).stat().st_size
            self.assertEqual(summary["file_size"], format_file_size(expected_bytes))
            self.assertTrue(any("Skipped download (>1GB)" in note for note in notes))
        finally:
            for file_path in folder.iterdir():
                file_path.unlink(missing_ok=True)
            folder.rmdir()

    @patch("collectors.AdcCollector.Storage")
    def test_update_storage_large_file_status(self, mock_storage: MagicMock) -> None:
        """Skipped large files set collected - large file status."""
        mock_storage.get.return_value = {"errors": ""}
        collector = AdcCollector()
        collector._update_storage(
            1,
            {"folder_path": "C:\\Data\\DRP000001", "_skipped_large_file": True, "_external_archive": False},
        )
        mock_storage.update_record.assert_called_once()
        fields = mock_storage.update_record.call_args[0][1]
        self.assertEqual(fields["status"], STATUS_COLLECTED_LARGE_FILE)

    @patch("collectors.AdcCollector.Storage")
    def test_update_storage_external_archive_status(self, mock_storage: MagicMock) -> None:
        """External-only datasets set collected - external archive status."""
        mock_storage.get.return_value = {"errors": ""}
        collector = AdcCollector()
        collector._update_storage(
            1,
            {"folder_path": "C:\\Data\\DRP000001", "_external_archive": True},
        )
        fields = mock_storage.update_record.call_args[0][1]
        self.assertEqual(fields["status"], STATUS_COLLECTED_EXTERNAL_ARCHIVE)

    @patch("collectors.AdcCollector.Storage")
    @patch("collectors.AdcCollector.create_output_folder")
    @patch("collectors.AdcCollector.extract_metadata")
    @patch("collectors.AdcCollector.record_warning")
    def test_collect_external_archive_skips_downloads(
        self,
        _mock_warning: MagicMock,
        mock_extract: MagicMock,
        mock_folder: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Link-only datasets save metadata and set external archive status."""
        mock_extract.return_value = {"title": "External dataset"}
        tmp = Path(__file__).parent / "_tmp_adc_external"
        tmp.mkdir(exist_ok=True)
        mock_folder.return_value = tmp
        mock_storage.get.return_value = {"errors": ""}

        api = MagicMock()
        api.fetch_article.return_value = {
            "title": "External dataset",
            "files": [{
                "name": "link.html",
                "size": 0,
                "is_link_only": True,
                "download_url": "https://example.ars.usda.gov/data",
            }],
        }
        collector = AdcCollector(api_client=api, inventory=AdcFileInventory())
        url = "https://agdatacommons.nal.usda.gov/articles/dataset/X/123"

        try:
            result = collector._collect(url, 15)
            self.assertTrue(result.get("_external_archive"))
            self.assertIn(
                "External data URL: https://example.ars.usda.gov/data",
                result.get("status_notes", ""),
            )
            collector._update_storage(15, result)
            fields = mock_storage.update_record.call_args[0][1]
            self.assertEqual(fields["status"], STATUS_COLLECTED_EXTERNAL_ARCHIVE)
        finally:
            for file_path in tmp.iterdir():
                file_path.unlink(missing_ok=True)
            tmp.rmdir()

    @patch("collectors.AdcCollector.record_error")
    @patch("collectors.AdcCollector.retry_http_call")
    @patch("collectors.AdcCollector.Storage")
    def test_run_sets_not_found_when_source_inaccessible(
        self,
        mock_storage: MagicMock,
        mock_retry: MagicMock,
        mock_record_error: MagicMock,
    ) -> None:
        """Source metadata 404 sets not_found status."""
        from utils.retry_http import SourceNotFoundError

        mock_storage.get.return_value = {
            "source_url": "https://agdatacommons.nal.usda.gov/articles/dataset/X/1",
            "status": "sourced",
        }
        mock_retry.side_effect = SourceNotFoundError("missing", status_code=404)

        AdcCollector(api_client=MagicMock()).run(1)

        mock_record_error.assert_called_once()
        self.assertEqual(
            mock_record_error.call_args.kwargs.get("status_value"),
            "not_found",
        )

    def test_save_catalog_html_writes_self_contained_html(self) -> None:
        """Catalog HTML is saved as a single file with embedded CSS."""
        collector = AdcCollector()
        folder = Path(__file__).parent / "_tmp_adc_catalog"
        folder.mkdir(exist_ok=True)
        source_url = (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        )
        article = {"title": "Example dataset", "description": "<p>Summary</p>"}
        try:
            collector._save_catalog_html(folder, article, source_url)
            html_path = folder / "catalog_detail.html"
            self.assertTrue(html_path.is_file())
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("Example dataset", html_text)
            self.assertIn("<style>", html_text)
            self.assertNotIn("<script", html_text.lower())
            self.assertNotIn('rel="stylesheet"', html_text.lower())
        finally:
            for file_path in folder.iterdir():
                file_path.unlink(missing_ok=True)
            folder.rmdir()
