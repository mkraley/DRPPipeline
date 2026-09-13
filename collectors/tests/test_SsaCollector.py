"""Tests for SsaCollector."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.SsaCollector import SsaCollector
from collectors.SsaFileDownloader import CATALOG_PDF_NAME
from utils.Args import Args
from utils.Logger import Logger

_FIXTURE = Path(__file__).parent / "fixtures" / "ssa_catalog_baby_names.html"
_URL = (
    "https://catalog.data.gov/dataset/"
    "baby-names-from-social-security-card-applications-national-data"
)


class TestSsaCollector(unittest.TestCase):
    """Tests for SSA collector orchestration."""

    def setUp(self) -> None:
        """Initialize Args and a collector instance."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Args._config["base_output_dir"] = str(Path(__file__).parent / "_tmp_ssa_output")
        Logger.initialize(log_level="WARNING")
        self.collector = SsaCollector(headless=True)

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv

    @patch("collectors.SsaCollector.record_error")
    def test_collect_rejects_non_catalog_url(self, mock_error: MagicMock) -> None:
        """Non-catalog URLs are rejected before fetch."""
        self.collector._page_downloader = MagicMock()
        result = self.collector._collect("https://www.ssa.gov/data/", 1, {})
        self.assertEqual(result, {})
        mock_error.assert_called()

    @patch("utils.IcpsrGeographicNormalizer.normalize_geographic_metadata")
    @patch("collectors.SsaCollector.create_output_folder")
    @patch("collectors.SsaCollector.UsfsPageDownloader")
    def test_collect_downloads_zip_and_saves_pdf(
        self,
        _mock_downloader_cls: MagicMock,
        mock_create_folder: MagicMock,
        mock_normalize_geo: MagicMock,
    ) -> None:
        """Catalog PDF, HTML resource PDF, and ZIP file are saved."""
        folder = Path(__file__).parent / "_tmp_ssa_collect"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        page_downloader = MagicMock()
        page_downloader.fetch_page_html.return_value = (
            200,
            _FIXTURE.read_text(encoding="utf-8"),
            "text/html",
            False,
        )
        page_downloader.url_to_pdf.return_value = True

        def _write(url: str, dest: Path) -> tuple[int, bool]:
            dest.write_bytes(b"PK\x03\x04")
            return 4, True

        def _titled_pdf(url: str, dest_dir: Path, fallback_stem: str = "page") -> Path:
            dest = dest_dir / "Background_Information_for_Popular_Names.pdf"
            dest.write_bytes(b"%PDF")
            return dest

        page_downloader.download_file.side_effect = _write
        page_downloader.url_to_titled_pdf.side_effect = _titled_pdf
        page_downloader.fetch_content_length.return_value = 4
        self.collector._page_downloader = page_downloader

        try:
            result = self.collector._collect(_URL, 3, {"source_url": _URL})
            self.assertEqual(result["title"][:10], "Baby Names")
            self.assertEqual(result["geographic_coverage"], "United States")
            mock_normalize_geo.assert_not_called()
            self.assertEqual(result["folder_path"], str(folder))
            self.assertIn("zip", result.get("extensions", ""))
            self.assertEqual(result["num_files"], 3)
            self.assertTrue((folder / "names.zip").is_file())
            page_downloader.url_to_pdf.assert_called_once()
            self.assertEqual(
                page_downloader.url_to_pdf.call_args.kwargs.get("open_details_selector"),
                "h2.complete-metadata-heading",
            )
            page_downloader.url_to_titled_pdf.assert_called_once()
            downloaded_urls = [
                call.args[0] for call in page_downloader.download_file.call_args_list
            ]
            self.assertEqual(
                downloaded_urls,
                ["https://www.ssa.gov/oact/babynames/names.zip"],
            )
            pdf_dest = page_downloader.url_to_pdf.call_args.args[1]
            self.assertEqual(pdf_dest.name, CATALOG_PDF_NAME)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    @patch("collectors.SsaCollector.record_error")
    @patch("collectors.SsaCollector.create_output_folder")
    def test_collect_html_only_saves_pdfs(
        self,
        mock_create_folder: MagicMock,
        mock_error: MagicMock,
    ) -> None:
        """HTML-only catalog pages still save catalog and landing-page PDFs."""
        folder = Path(__file__).parent / "_tmp_ssa_nofile"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        page_downloader = MagicMock()
        page_downloader.fetch_page_html.return_value = (
            200,
            """
            <html><body>
            <script type="application/ld+json">
            {"@type":"Dataset","name":"Index",
             "distribution":[{"contentUrl":"https://www.ssa.gov/x.html",
                              "encodingFormat":"text/html"}]}
            </script>
            <h1>Index</h1>
            </body></html>
            """,
            "text/html",
            False,
        )
        page_downloader.url_to_pdf.return_value = True

        def _titled_pdf(url: str, dest_dir: Path, fallback_stem: str = "page") -> Path:
            dest = dest_dir / "Index.pdf"
            dest.write_bytes(b"%PDF")
            return dest

        page_downloader.url_to_titled_pdf.side_effect = _titled_pdf
        self.collector._page_downloader = page_downloader
        try:
            result = self.collector._collect(_URL, 4, {})
            self.assertEqual(result.get("title"), "Index")
            self.assertEqual(result.get("num_files"), 2)
            mock_error.assert_not_called()
            page_downloader.download_file.assert_not_called()
            page_downloader.url_to_titled_pdf.assert_called_once()
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    @patch("collectors.SsaCollector.record_error")
    @patch("collectors.SsaCollector.create_output_folder")
    def test_collect_errors_when_no_resources(
        self,
        mock_create_folder: MagicMock,
        mock_error: MagicMock,
    ) -> None:
        """Pages with no files and no HTML resources record an error."""
        folder = Path(__file__).parent / "_tmp_ssa_empty"
        folder.mkdir(exist_ok=True)
        mock_create_folder.return_value = folder
        page_downloader = MagicMock()
        page_downloader.fetch_page_html.return_value = (
            200,
            """
            <html><body>
            <script type="application/ld+json">
            {"@type":"Dataset","name":"Empty"}
            </script>
            <h1>Empty</h1>
            </body></html>
            """,
            "text/html",
            False,
        )
        page_downloader.url_to_pdf.return_value = True
        self.collector._page_downloader = page_downloader
        try:
            result = self.collector._collect(_URL, 5, {})
            self.assertEqual(result.get("title"), "Empty")
            mock_error.assert_called()
            page_downloader.download_file.assert_not_called()
            page_downloader.url_to_titled_pdf.assert_not_called()
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
