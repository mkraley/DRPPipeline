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


if __name__ == "__main__":
    unittest.main()
