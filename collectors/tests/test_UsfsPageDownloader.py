"""Tests for UsfsPageDownloader."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from collectors.UsfsPageDownloader import UsfsPageDownloader


class TestUsfsPageDownloader(unittest.TestCase):
    @patch.object(UsfsPageDownloader, "_restart_browser", return_value=False)
    def test_download_file_returns_false_when_browser_unavailable(
        self, mock_restart: MagicMock
    ) -> None:
        downloader = UsfsPageDownloader()
        size, ok = downloader.download_file(
            "https://www.fs.usda.gov/rds/archive/products/RDS/x.zip",
            Path("x.zip"),
        )
        self.assertEqual(size, 0)
        self.assertFalse(ok)
        mock_restart.assert_called_once()

    @patch.object(UsfsPageDownloader, "close")
    @patch.object(UsfsPageDownloader, "_ensure_browser", return_value=True)
    def test_restart_browser_closes_before_relaunch(
        self, mock_ensure: MagicMock, mock_close: MagicMock
    ) -> None:
        downloader = UsfsPageDownloader()
        self.assertTrue(downloader._restart_browser())
        mock_close.assert_called_once()
        mock_ensure.assert_called_once()

    @patch.object(UsfsPageDownloader, "_ensure_browser", return_value=True)
    def test_fetch_content_length_returns_header_value(self, mock_ensure: MagicMock) -> None:
        """Non-ROSA P HEAD response Content-Length is parsed as an integer."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.headers = {"content-length": "4096"}
        mock_page.request.head.return_value = mock_response
        downloader._session.new_page = MagicMock(return_value=mock_page)

        size = downloader.fetch_content_length(
            "https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"
        )

        self.assertEqual(size, 4096)
        mock_page.request.head.assert_called_once()
        mock_page.close.assert_called_once()

    def test_fetch_content_length_rosap_uses_chrome_probe(self) -> None:
        """ROSA P Content-Length uses Chrome-impersonated HEAD."""
        downloader = UsfsPageDownloader()
        with patch(
            "utils.ChromeRangeDownload.probe_content_length", return_value=2024010110
        ) as mock_probe:
            size = downloader.fetch_content_length(
                "https://rosap.ntl.bts.gov/view/dot/7547/dot_7547_DS1.zip"
            )
        self.assertEqual(size, 2024010110)
        mock_probe.assert_called_once()

    @patch.object(UsfsPageDownloader, "_ensure_browser", return_value=False)
    def test_fetch_content_length_returns_none_without_browser(
        self, mock_ensure: MagicMock
    ) -> None:
        """Return None when Chromium is unavailable for non-ROSA P hosts."""
        downloader = UsfsPageDownloader()
        self.assertIsNone(
            downloader.fetch_content_length(
                "https://www.fs.usda.gov/rds/archive/products/RDS/x.zip"
            )
        )

    @patch.object(UsfsPageDownloader, "_restart_browser", return_value=True)
    def test_download_file_rosap_uses_chrome_ranges(
        self, mock_restart: MagicMock
    ) -> None:
        """ROSA P download_file skips Playwright and uses Chrome Ranges."""
        downloader = UsfsPageDownloader()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "f.zip"
            with patch(
                "utils.ChromeRangeDownload.download_via_chrome_ranges",
                return_value=(9, True),
            ) as mock_chrome:
                size, ok = downloader.download_file(
                    "https://rosap.ntl.bts.gov/view/dot/1/f.zip",
                    dest,
                )
        self.assertTrue(ok)
        self.assertEqual(size, 9)
        mock_chrome.assert_called_once()
        mock_restart.assert_not_called()

    @patch.object(UsfsPageDownloader, "_restart_browser", return_value=True)
    def test_download_file_xml_uses_api_request(
        self, mock_restart: MagicMock
    ) -> None:
        """XML is fetched with Playwright GET because Chromium will not download it."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.body.return_value = b"<report/>"
        mock_page.request.get.return_value = mock_response
        downloader._session.new_page = MagicMock(return_value=mock_page)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "report.xml"
            size, ok = downloader.download_file(
                "https://www.ssa.gov/appeals/DataSets/archive/05_FY2025/"
                "05_October_Average_Processing_Time_Report.xml",
                dest,
            )
            self.assertTrue(ok)
            self.assertEqual(size, 9)
            self.assertEqual(dest.read_bytes(), b"<report/>")
        mock_page.request.get.assert_called_once()
        mock_page.expect_download.assert_not_called()
        mock_restart.assert_called_once()

    @patch.object(UsfsPageDownloader, "_restart_browser", return_value=True)
    def test_download_file_json_uses_api_request(
        self, mock_restart: MagicMock
    ) -> None:
        """JSON is fetched with Playwright GET, not expect_download."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.body.return_value = b'{"ok":true}'
        mock_page.request.get.return_value = mock_response
        downloader._session.new_page = MagicMock(return_value=mock_page)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "data.json"
            size, ok = downloader.download_file(
                "https://www.ssa.gov/data/foo.json",
                dest,
            )
            self.assertTrue(ok)
            self.assertEqual(size, 11)
            self.assertEqual(dest.read_bytes(), b'{"ok":true}')
        mock_page.expect_download.assert_not_called()
        mock_restart.assert_called_once()

    @patch.object(UsfsPageDownloader, "_restart_browser", return_value=True)
    def test_download_file_zip_uses_expect_download(
        self, mock_restart: MagicMock
    ) -> None:
        """ZIP files still use the Playwright download event."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        mock_download = MagicMock()

        def _save_as(path: str) -> None:
            Path(path).write_bytes(b"PK\x03\x04")

        mock_download.save_as.side_effect = _save_as
        mock_context = MagicMock()
        mock_context.__enter__.return_value = MagicMock(value=mock_download)
        mock_context.__exit__.return_value = False
        mock_page.expect_download.return_value = mock_context
        downloader._session.new_page = MagicMock(return_value=mock_page)
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "names.zip"
            size, ok = downloader.download_file(
                "https://www.ssa.gov/oact/babynames/names.zip",
                dest,
            )
            self.assertTrue(ok)
            self.assertEqual(size, 4)
            self.assertEqual(dest.read_bytes(), b"PK\x03\x04")
        mock_page.expect_download.assert_called_once()
        mock_page.request.get.assert_not_called()
        mock_restart.assert_called_once()

    @patch.object(UsfsPageDownloader, "_ensure_browser", return_value=True)
    def test_url_to_pdf_opens_details(self, _mock_ensure: MagicMock) -> None:
        """Complete Metadata (or any details ancestor) is opened before print."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        downloader._session.new_page = MagicMock(return_value=mock_page)

        def _pdf(**kwargs: object) -> None:
            Path(str(kwargs["path"])).write_bytes(b"%PDF")

        mock_page.pdf.side_effect = _pdf
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "c.pdf"
            ok = downloader.url_to_pdf(
                "https://catalog.data.gov/dataset/x",
                dest,
                open_details_selector="h2.complete-metadata-heading",
            )
        self.assertTrue(ok)
        mock_page.locator.assert_called_with("h2.complete-metadata-heading")
        mock_page.locator.return_value.first.evaluate.assert_called_once()

    @patch.object(UsfsPageDownloader, "_ensure_browser", return_value=True)
    def test_url_to_titled_pdf_uses_page_title(self, _mock_ensure: MagicMock) -> None:
        """HTML resource PDFs are named from the document title."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        mock_page.title.return_value = "Background Information for Popular Names"
        downloader._session.new_page = MagicMock(return_value=mock_page)

        def _pdf(**kwargs: object) -> None:
            Path(str(kwargs["path"])).write_bytes(b"%PDF")

        mock_page.pdf.side_effect = _pdf
        with tempfile.TemporaryDirectory() as tmp:
            dest = downloader.url_to_titled_pdf(
                "https://www.ssa.gov/oact/babynames/limits.html",
                Path(tmp),
                fallback_stem="limits",
            )
        self.assertIsNotNone(dest)
        assert dest is not None
        self.assertEqual(dest.name, "Background_Information_for_Popular_Names.pdf")


if __name__ == "__main__":
    unittest.main()
