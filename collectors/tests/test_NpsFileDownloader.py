"""Tests for NPS Digital File downloads."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collectors.NpsDownloadPlan import NpsPlannedFile
from collectors.NpsFileDownloader import NpsFileDownloader, _looks_like_html, count_files
from utils.Args import Args
from utils.Logger import Logger


class TestNpsFileDownloader(unittest.TestCase):
    """Tests for budgeted IRMA file downloads."""

    def setUp(self) -> None:
        """Initialize Args for download timeouts."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    def test_looks_like_html_detects_login_page(self) -> None:
        """HTML bodies are treated as restricted login pages."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.pdf"
            path.write_bytes(b"<!DOCTYPE html><html><body>Sign in</body></html>")
            self.assertTrue(_looks_like_html(path))
            path.write_bytes(b"%PDF-1.4 fake")
            self.assertFalse(_looks_like_html(path))

    @patch("collectors.NpsFileDownloader.download_via_url")
    def test_download_files_writes_dest(self, mock_download) -> None:
        """Successful downloads land in the product subfolder."""
        def _write(_url: str, dest: Path, **_kwargs: object) -> tuple[int, bool]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"%PDF-1.4")
            return 8, True

        mock_download.side_effect = _write
        entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/147164",
            filename="report.pdf",
            relative_dir="663485_report",
            size_bytes=8,
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            notes, skipped, total, exts = NpsFileDownloader().download_files(1, folder, [entry])
            dest = folder / "663485_report" / "report.pdf"
            self.assertTrue(dest.is_file())
        self.assertFalse(skipped)
        self.assertEqual(notes, [])
        self.assertIn("pdf", exts)
        self.assertGreater(total, 0)

    @patch("collectors.NpsFileDownloader.record_error")
    @patch("collectors.NpsFileDownloader.download_via_url")
    def test_html_download_is_deleted(self, mock_download, mock_error) -> None:
        """Login HTML is not kept as a dataset file."""
        def _write(_url: str, dest: Path, **_kwargs: object) -> tuple[int, bool]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"<html>login</html>")
            return 18, True

        mock_download.side_effect = _write
        entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/1",
            filename="secret.csv",
            relative_dir="_project_files",
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            NpsFileDownloader().download_files(7, folder, [entry])
            self.assertFalse((folder / "_project_files" / "secret.csv").exists())
        mock_error.assert_called()

    def test_count_files_includes_nested_folders(self) -> None:
        """num_files inventory counts regular files under product subfolders."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "project_metadata.json").write_text("{}", encoding="utf-8")
            nested = root / "pkg"
            nested.mkdir()
            (nested / "report.pdf").write_bytes(b"%PDF-1.4")
            (nested / "product_metadata.json").write_text("{}", encoding="utf-8")
            self.assertEqual(count_files(root), 3)


if __name__ == "__main__":
    unittest.main()
