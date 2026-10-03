"""Tests for NPS Digital File downloads."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collectors.NpsDownloadPlan import NpsPlannedFile
from collectors.NpsFileDownloader import NpsFileDownloader, count_files, projected_file_count, projected_folder_bytes
from utils.Args import Args
from utils.Errors import ProjectAbort
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
        from collectors.NpsHtmlDownloadCheck import unexpected_html_message

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "file.pdf"
            path.write_bytes(b"<!DOCTYPE html><html><body>Sign in</body></html>")
            self.assertIsNotNone(
                unexpected_html_message(path, filename="file.pdf", url="https://x")
            )
            path.write_bytes(b"%PDF-1.4 fake")
            self.assertIsNone(
                unexpected_html_message(path, filename="file.pdf", url="https://x")
            )

    def test_looks_like_html_allows_html_extension(self) -> None:
        """Real .html Digital Files are not treated as restricted pages."""
        from collectors.NpsHtmlDownloadCheck import unexpected_html_message

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "AK06_AMoN_SummaryTools_Report.html"
            path.write_bytes(b"<!DOCTYPE html><html><body>Report</body></html>")
            self.assertIsNone(
                unexpected_html_message(
                    path,
                    filename="AK06_AMoN_SummaryTools_Report.html",
                    url="https://x",
                )
            )

    @patch("collectors.NpsFileDownloader.record_error")
    @patch("collectors.NpsFileDownloader.download_via_url")
    def test_html_extension_download_is_kept(self, mock_download, mock_error) -> None:
        """IRMA Digital Files that are HTML are retained on disk."""
        def _write(_url: str, dest: Path, **_kwargs: object) -> tuple[int, bool]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"<!DOCTYPE html><html><body>ok</body></html>")
            return 40, True

        mock_download.side_effect = _write
        entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/761255",
            filename="AK06_AMoN_SummaryTools_Report.html",
            relative_dir="",
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            NpsFileDownloader().download_files(9, folder, [entry])
            dest = folder / "AK06_AMoN_SummaryTools_Report.html"
            self.assertTrue(dest.is_file())
            self.assertFalse((folder / "_project_files").exists())
        mock_error.assert_not_called()

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

    @patch("utils.Errors.record_error")
    @patch("collectors.NpsFileDownloader.download_via_url")
    def test_html_download_is_deleted(self, mock_download, mock_error) -> None:
        """Login HTML is not kept, and collection of this project stops."""
        def _write(url: str, dest: Path, **_kwargs: object) -> tuple[int, bool]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if url.endswith("/1"):
                dest.write_bytes(b"<html>login</html>")
            else:
                dest.write_bytes(b"%PDF-1.4")
            return dest.stat().st_size, True

        mock_download.side_effect = _write
        html_entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/1",
            filename="secret.csv",
            relative_dir="",
        )
        pdf_entry = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/2",
            filename="ok.pdf",
            relative_dir="",
            size_bytes=8,
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with self.assertRaises(ProjectAbort):
                NpsFileDownloader().download_files(7, folder, [html_entry, pdf_entry])
            self.assertFalse((folder / "secret.csv").exists())
            self.assertFalse((folder / "ok.pdf").exists())
            self.assertFalse((folder / "_project_files").exists())
        mock_error.assert_called()
        self.assertIn("Download returned HTML", mock_error.call_args.args[1])

    @patch("collectors.NpsFileDownloader.would_exceed_download_budget")
    @patch("collectors.NpsFileDownloader.download_via_url")
    def test_existing_files_count_toward_budget_across_batches(
        self,
        mock_download: object,
        mock_budget,
    ) -> None:
        """On-disk files from earlier Product batches count toward the 1 GB cap."""
        mock_budget.side_effect = lambda used, _expected: used >= 50
        nxt = NpsPlannedFile(
            url="https://irma.nps.gov/DataStore/DownloadFile/2",
            filename="next.bin",
            relative_dir="b",
            size_bytes=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            prior = folder / "a" / "already.bin"
            prior.parent.mkdir(parents=True)
            prior.write_bytes(b"x" * 50)
            notes, skipped, _total, _exts = NpsFileDownloader().download_files(
                3, folder, [nxt]
            )
            self.assertTrue(skipped)
            self.assertFalse((folder / nxt.relative_dir / nxt.filename).exists())
            self.assertTrue(notes)
            mock_download.assert_not_called()

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

    def test_projected_folder_bytes_adds_missing_catalog_sizes(self) -> None:
        """file_size includes catalog bytes for files that were not downloaded."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "have.pdf").write_bytes(b"x" * 10)
            files = [
                NpsPlannedFile(
                    url="https://example.com/have",
                    filename="have.pdf",
                    relative_dir="",
                    size_bytes=999,
                ),
                NpsPlannedFile(
                    url="https://example.com/miss",
                    filename="miss.zip",
                    relative_dir="pkg",
                    size_bytes=50,
                ),
            ]
            self.assertEqual(projected_folder_bytes(root, files), 60)
            self.assertEqual(projected_file_count(root, files), 2)

    def test_projected_folder_bytes_counts_same_name_in_another_product(self) -> None:
        """A downloaded name in one product does not hide a missing copy elsewhere."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            downloaded = root / "alpha"
            downloaded.mkdir()
            (downloaded / "data.zip").write_bytes(b"x" * 10)
            files = [
                NpsPlannedFile(
                    url="https://example.com/alpha",
                    filename="data.zip",
                    relative_dir="alpha",
                    size_bytes=999,
                ),
                NpsPlannedFile(
                    url="https://example.com/beta",
                    filename="data.zip",
                    relative_dir="beta",
                    size_bytes=50,
                ),
            ]
            self.assertEqual(projected_folder_bytes(root, files), 60)
            self.assertEqual(projected_file_count(root, files), 2)


if __name__ == "__main__":
    unittest.main()
