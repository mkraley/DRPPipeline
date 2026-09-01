"""Tests for UsfsPageDownloader."""

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
        """HEAD response Content-Length is parsed as an integer."""
        downloader = UsfsPageDownloader()
        mock_page = MagicMock()
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.headers = {"content-length": "4096"}
        mock_page.request.head.return_value = mock_response
        downloader._session.new_page = MagicMock(return_value=mock_page)

        size = downloader.fetch_content_length(
            "https://rosap.ntl.bts.gov/view/dot/54854/dot_54854_DS2.txt"
        )

        self.assertEqual(size, 4096)
        mock_page.request.head.assert_called_once()
        mock_page.close.assert_called_once()

    @patch.object(UsfsPageDownloader, "_ensure_browser", return_value=False)
    def test_fetch_content_length_returns_none_without_browser(
        self, mock_ensure: MagicMock
    ) -> None:
        """Return None when Chromium is unavailable."""
        downloader = UsfsPageDownloader()
        self.assertIsNone(
            downloader.fetch_content_length(
                "https://rosap.ntl.bts.gov/view/dot/54854/dot_54854_DS2.txt"
            )
        )


if __name__ == "__main__":
    unittest.main()
