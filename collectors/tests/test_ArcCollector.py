"""Tests for ArcCollector download size policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.ArcCollector import (
    STATUS_COLLECTED_EXTERNAL_ARCHIVE,
    STATUS_COLLECTED_LARGE_FILE,
    ArcCollector,
)
from sourcing.ArcFileInventory import MAX_DOWNLOAD_BYTES


class TestArcCollector(unittest.TestCase):
    """Tests for ARC collector behavior."""

    def setUp(self) -> None:
        """Initialize Args and Logger for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("collectors.ArcCollector.download_via_url")
    def test_skips_download_over_1gb(self, mock_download: MagicMock) -> None:
        """Files over 1 GB are skipped and noted in status_notes."""
        catalog_bytes = MAX_DOWNLOAD_BYTES + 1
        collector = ArcCollector()
        folder = Path(__file__).parent / "_tmp_arc_test"
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

    @patch("collectors.ArcCollector.download_via_url", return_value=(128, True))
    def test_downloads_small_file(self, mock_download: MagicMock) -> None:
        """Files under 1 GB are downloaded."""
        collector = ArcCollector()
        folder = Path(__file__).parent / "_tmp_arc_dl"
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

    @patch("collectors.ArcCollector.Storage")
    def test_update_storage_large_file_status(self, mock_storage: MagicMock) -> None:
        """Skipped large files set collected - large file status."""
        mock_storage.get.return_value = {"errors": ""}
        collector = ArcCollector()
        collector._update_storage(
            1,
            {"folder_path": "C:\\Data\\DRP000001", "_skipped_large_file": True, "_external_archive": False},
        )
        mock_storage.update_record.assert_called_once()
        fields = mock_storage.update_record.call_args[0][1]
        self.assertEqual(fields["status"], STATUS_COLLECTED_LARGE_FILE)

    @patch("collectors.ArcCollector.Storage")
    def test_update_storage_external_archive_status(self, mock_storage: MagicMock) -> None:
        """External-only datasets set collected - external archive status."""
        mock_storage.get.return_value = {"errors": ""}
        collector = ArcCollector()
        collector._update_storage(
            1,
            {"folder_path": "C:\\Data\\DRP000001", "_external_archive": True},
        )
        fields = mock_storage.update_record.call_args[0][1]
        self.assertEqual(fields["status"], STATUS_COLLECTED_EXTERNAL_ARCHIVE)

    def test_save_catalog_pdf_writes_html_and_requests_extension_pdf(self) -> None:
        """Catalog HTML is saved; missing PDF triggers extension workflow hint."""
        collector = ArcCollector()
        folder = Path(__file__).parent / "_tmp_arc_catalog"
        folder.mkdir(exist_ok=True)
        source_url = (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Example/24667896"
        )
        article = {"title": "Example dataset", "description": "<p>Summary</p>"}
        try:
            with patch("collectors.ArcCollector.record_warning") as mock_warn:
                collector._save_catalog_pdf(1, folder, article, source_url)
            html_path = folder / "catalog_detail.html"
            self.assertTrue(html_path.is_file())
            self.assertIn("Example dataset", html_path.read_text(encoding="utf-8"))
            mock_warn.assert_called_once()
            self.assertIn("Save as PDF", mock_warn.call_args[0][1])
        finally:
            for file_path in folder.iterdir():
                file_path.unlink(missing_ok=True)
            folder.rmdir()
