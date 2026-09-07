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


if __name__ == "__main__":
    unittest.main()
