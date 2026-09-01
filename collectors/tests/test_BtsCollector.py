"""Tests for BtsCollector."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

from collectors.BtsCollector import BtsCollector, _CATALOG_PDF_NAME
from utils.Args import Args
from utils.Logger import Logger
from utils.collector_status import MAX_DOWNLOAD_BYTES, STATUS_COLLECTED_LARGE_FILE

_FIXTURE = Path(__file__).parent / "fixtures" / "bts_detail_54854.html"


class TestBtsCollector(unittest.TestCase):
    """Tests for BTS collector orchestration."""

    def setUp(self) -> None:
        """Initialize Args and a collector instance."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Args._config["base_output_dir"] = str(Path(__file__).parent / "_tmp_bts_output")
        Logger.initialize(log_level="WARNING")
        self.collector = BtsCollector(headless=True)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("collectors.BtsCollector.create_output_folder")
    @patch("collectors.BtsCollector.scan_zip_extensions_in_folder")
    @patch("collectors.BtsCollector.UsfsPageDownloader")
    def test_collect_enriches_extensions_from_zip_scan(
        self,
        mock_downloader_cls: MagicMock,
        mock_zip_scan: MagicMock,
        mock_create_folder: MagicMock,
    ) -> None:
        """Zip member extensions augment metadata without changing file counts."""
        from utils.zip_extension_scan import ZipExtensionScanResult

        folder = Path(__file__).parent / "_tmp_bts_zip_ext"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        mock_zip_scan.return_value = ZipExtensionScanResult(
            extensions={"shp", "dbf"},
            archives_scanned=1,
        )

        page_downloader = MagicMock()
        page_downloader.fetch_page_html.return_value = (200, _FIXTURE.read_text(encoding="utf-8"), None, False)
        page_downloader.url_to_pdf.return_value = True
        def _fake_download(_url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"x" * 8)
            return 8, True

        page_downloader.download_file.side_effect = _fake_download
        mock_downloader_cls.return_value = page_downloader

        self.collector._page_downloader = page_downloader
        result = self.collector._collect(
            "https://rosap.ntl.bts.gov/view/dot/54854",
            6,
            {"source_url": "https://rosap.ntl.bts.gov/view/dot/54854"},
        )

        self.assertIn("shp", result.get("extensions", ""))
        self.assertIn("dbf", result.get("extensions", ""))
        self.assertGreaterEqual(result.get("num_files", 0), 1)

        shutil.rmtree(folder, ignore_errors=True)

    @patch("collectors.BtsCollector.create_output_folder")
    @patch("collectors.BtsCollector.UsfsPageDownloader")
    def test_collect_downloads_files_and_sets_metadata(
        self,
        mock_downloader_cls: MagicMock,
        mock_create_folder: MagicMock,
    ) -> None:
        """End-to-end collection writes metadata and downloads catalog plus data files."""
        folder = Path(__file__).parent / "_tmp_bts_collect"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder

        page_downloader = MagicMock()
        page_downloader.fetch_page_html.return_value = (200, _FIXTURE.read_text(encoding="utf-8"), None, False)
        page_downloader.url_to_pdf.return_value = True

        def _fake_download(url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"x" * 16)
            return 16, True

        page_downloader.download_file.side_effect = _fake_download
        mock_downloader_cls.return_value = page_downloader

        self.collector._page_downloader = page_downloader
        result = self.collector._collect(
            "https://rosap.ntl.bts.gov/view/dot/54854",
            6,
            {"source_url": "https://rosap.ntl.bts.gov/view/dot/54854"},
        )

        self.assertEqual(result["folder_path"], str(folder))
        self.assertIn("title", result)
        self.assertIn("summary", result)
        self.assertTrue((folder / _CATALOG_PDF_NAME).exists() or page_downloader.url_to_pdf.called)
        self.assertGreaterEqual(result.get("num_files", 0), 1)
        self.assertIn("download_date", result)

        shutil.rmtree(folder, ignore_errors=True)

    @patch("collectors.BtsCollector.Logger")
    def test_download_log_probes_size_for_supporting_files(
        self, mock_logger: MagicMock
    ) -> None:
        """Supporting files without catalog size log probed Content-Length."""
        page_downloader = MagicMock()
        page_downloader.fetch_content_length.return_value = 2048

        def _write_download(_url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"x" * 128)
            return 128, True

        page_downloader.download_file.side_effect = _write_download
        folder = Path(__file__).parent / "_tmp_bts_dl_probe"
        folder.mkdir(exist_ok=True)
        size_cache: dict[str, int | None] = {}
        try:
            from collectors.BtsMetadataExtractor import BtsDownloadFile

            self.collector._download_files(
                6,
                page_downloader,
                folder,
                [
                    BtsDownloadFile(
                        label="README File",
                        url="https://rosap.ntl.bts.gov/view/dot/54854/dot_54854_DS2.txt",
                        filename="dot_54854_DS2.txt",
                        size_bytes=None,
                        is_main=False,
                    )
                ],
                size_cache,
            )
            page_downloader.fetch_content_length.assert_called_once()
            mock_logger.info.assert_any_call(
                "Downloading %s file: %s (%s)",
                "supporting",
                "README_File.txt",
                ANY,
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    @patch("collectors.BtsCollector.Logger")
    def test_download_log_includes_expected_size(self, mock_logger: MagicMock) -> None:
        """Downloading log includes catalog file size when known."""
        page_downloader = MagicMock()

        def _write_download(_url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"x" * 128)
            return 128, True

        page_downloader.download_file.side_effect = _write_download
        folder = Path(__file__).parent / "_tmp_bts_dl_log"
        folder.mkdir(exist_ok=True)
        size_cache: dict[str, int | None] = {}
        try:
            from collectors.BtsMetadataExtractor import BtsDownloadFile

            self.collector._download_files(
                6,
                page_downloader,
                folder,
                [
                    BtsDownloadFile(
                        label="Main document",
                        url="https://rosap.ntl.bts.gov/view/dot/1/data.zip",
                        filename="data.zip",
                        size_bytes=128,
                        is_main=True,
                    )
                ],
                size_cache,
            )
            mock_logger.info.assert_any_call(
                "Downloading %s file: %s (%s)",
                "main",
                "data.zip",
                ANY,
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_skips_download_over_1gb(self) -> None:
        """Main files over 1 GB are skipped with a status note."""
        page_downloader = MagicMock()
        folder = Path(__file__).parent / "_tmp_bts_large"
        folder.mkdir(exist_ok=True)
        size_cache: dict[str, int | None] = {}
        try:
            from collectors.BtsMetadataExtractor import BtsDownloadFile

            notes, skipped_large, inventory_bytes, _exts = self.collector._download_files(
                6,
                page_downloader,
                folder,
                [
                    BtsDownloadFile(
                        label="Main document",
                        url="https://rosap.ntl.bts.gov/view/dot/78551/dot_78551_DS1.zip",
                        filename="dot_78551_DS1.zip",
                        size_bytes=MAX_DOWNLOAD_BYTES + 1,
                        is_main=True,
                    )
                ],
                size_cache,
            )
            page_downloader.download_file.assert_not_called()
            self.assertTrue(skipped_large)
            self.assertTrue(any("Skipped download (>1GB)" in note for note in notes))
            self.assertTrue(any("Remaining downloads:" in note for note in notes))
            self.assertGreater(inventory_bytes, MAX_DOWNLOAD_BYTES)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_stops_when_cumulative_download_exceeds_1gb(self) -> None:
        """Defer remaining files once cumulative downloads exceed the 1 GB budget."""
        page_downloader = MagicMock()
        folder = Path(__file__).parent / "_tmp_bts_cumulative"
        folder.mkdir(exist_ok=True)
        size_cache: dict[str, int | None] = {}
        try:
            from collectors.BtsMetadataExtractor import BtsDownloadFile

            first_size = 600 * 1024 * 1024
            second_size = 500 * 1024 * 1024

            def _fake_download(url: str, dest: Path) -> tuple[int, bool]:
                if dest.name == "first.zip":
                    dest.write_bytes(b"x" * first_size)
                else:
                    dest.write_bytes(b"x" * second_size)
                return dest.stat().st_size, True

            page_downloader.download_file.side_effect = _fake_download
            page_downloader.fetch_content_length.return_value = None

            notes, skipped_large, inventory_bytes, _exts = self.collector._download_files(
                6,
                page_downloader,
                folder,
                [
                    BtsDownloadFile(
                        label="Main document",
                        url="https://rosap.ntl.bts.gov/view/dot/1/first.zip",
                        filename="first.zip",
                        size_bytes=first_size,
                        is_main=True,
                    ),
                    BtsDownloadFile(
                        label="Supporting",
                        url="https://rosap.ntl.bts.gov/view/dot/1/second.zip",
                        filename="second.zip",
                        size_bytes=second_size,
                        is_main=False,
                    ),
                    BtsDownloadFile(
                        label="Supporting",
                        url="https://rosap.ntl.bts.gov/view/dot/1/third.zip",
                        filename="third.zip",
                        size_bytes=1024,
                        is_main=False,
                    ),
                ],
                size_cache,
            )

            self.assertTrue(skipped_large)
            self.assertTrue((folder / "first.zip").is_file())
            self.assertFalse((folder / "second.zip").is_file())
            self.assertTrue(any("second.zip" in note for note in notes))
            self.assertTrue(any("third.zip" in note for note in notes))
            self.assertTrue(any("500.0 MB" in note for note in notes))
            self.assertTrue(any("Remaining downloads:" in note for note in notes))
            self.assertEqual(page_downloader.download_file.call_count, 1)
            self.assertGreater(inventory_bytes, first_size)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    @patch("collectors.CollectorBase.merge_result_to_storage")
    @patch("collectors.BtsCollector.UsfsPageDownloader")
    def test_run_marks_large_file_status(
        self,
        mock_downloader_cls: MagicMock,
        mock_merge: MagicMock,
    ) -> None:
        """Inventory status mode forwards skipped-large-file flag to storage merge."""
        page_downloader = MagicMock()
        mock_downloader_cls.return_value = page_downloader

        collector = BtsCollector(headless=True)

        def _collect(_url: str, _drpid: int, _record: dict) -> dict:
            return {
                "folder_path": "C:\\DataRescue\\BTSData\\6",
                "_skipped_large_file": True,
            }

        with patch.object(collector, "load_project", return_value=({"source_url": "https://rosap.ntl.bts.gov/view/dot/78551"}, "https://rosap.ntl.bts.gov/view/dot/78551")):
            with patch.object(collector, "_collect", side_effect=_collect):
                collector.run(6)

        mock_merge.assert_called_once()
        result = mock_merge.call_args[0][1]
        self.assertTrue(result.get("_skipped_large_file"))


if __name__ == "__main__":
    unittest.main()
