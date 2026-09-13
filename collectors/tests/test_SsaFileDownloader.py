"""Tests for SsaFileDownloader."""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.SsaFileDownloader import SsaFileDownloader, destination_filename
from collectors.SsaMetadataExtractor import SsaDownloadFile
from utils.Logger import Logger
from utils.collector_status import MAX_DOWNLOAD_BYTES


class TestSsaFileDownloader(unittest.TestCase):
    """Tests for SSA file naming and the 1 GB download budget."""

    def setUp(self) -> None:
        """Initialize logging used by download status messages."""
        Logger.initialize(log_level="WARNING")

    def test_destination_filename_uses_url_basename(self) -> None:
        """URL path tail becomes the on-disk name, not the Resource N label."""
        entry = SsaDownloadFile(
            label="Resource 2",
            url="https://www.ssa.gov/oact/babynames/names.zip",
            filename="names.zip",
        )
        self.assertEqual(destination_filename(entry), "names.zip")

    def test_skips_download_over_1gb(self) -> None:
        """Files over 1 GB are skipped with a status note."""
        page_downloader = MagicMock()
        folder = Path(__file__).parent / "_tmp_ssa_large"
        folder.mkdir(exist_ok=True)
        downloader = SsaFileDownloader()
        try:
            notes, skipped, _bytes, _exts = downloader.download_files(
                1,
                page_downloader,
                folder,
                [
                    SsaDownloadFile(
                        label="Huge",
                        url="https://www.ssa.gov/huge.zip",
                        filename="huge.zip",
                        size_bytes=MAX_DOWNLOAD_BYTES + 1,
                    )
                ],
                {},
            )
            self.assertTrue(skipped)
            self.assertTrue(any("Skipped download" in line for line in notes))
            page_downloader.download_file.assert_not_called()
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_downloads_small_file(self) -> None:
        """Small files are written to the project folder."""
        page_downloader = MagicMock()

        def _write(_url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"zip-bytes")
            return 9, True

        page_downloader.download_file.side_effect = _write
        page_downloader.fetch_content_length.return_value = 9
        folder = Path(__file__).parent / "_tmp_ssa_small"
        folder.mkdir(exist_ok=True)
        downloader = SsaFileDownloader()
        try:
            notes, skipped, inventory_bytes, exts = downloader.download_files(
                1,
                page_downloader,
                folder,
                [
                    SsaDownloadFile(
                        label="National names",
                        url="https://www.ssa.gov/oact/babynames/names.zip",
                        filename="names.zip",
                        size_bytes=9,
                    )
                ],
                {},
            )
            self.assertFalse(skipped)
            self.assertEqual(notes, [])
            self.assertIn("zip", exts)
            dest = folder / "names.zip"
            self.assertTrue(dest.is_file())
            self.assertGreaterEqual(inventory_bytes, 9)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def test_save_catalog_pdf_expands_complete_metadata(self) -> None:
        """Catalog PDF print opens the Complete Metadata details section."""
        page_downloader = MagicMock()
        page_downloader.url_to_pdf.return_value = True
        folder = Path(__file__).parent / "_tmp_ssa_pdf"
        folder.mkdir(exist_ok=True)
        downloader = SsaFileDownloader()
        try:
            ok = downloader.save_catalog_pdf(
                page_downloader,
                folder,
                "https://catalog.data.gov/dataset/baby-names",
            )
            self.assertTrue(ok)
            self.assertEqual(
                page_downloader.url_to_pdf.call_args.kwargs["open_details_selector"],
                "h2.complete-metadata-heading",
            )
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
