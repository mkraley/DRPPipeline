"""Tests for UsfsCollector download size policy."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from utils.Args import Args
from utils.Logger import Logger

from collectors.UsfsCollector import (
    MAX_DOWNLOAD_BYTES,
    UsfsCollector,
    _PDF_NAMES,
)


class TestUsfsCollector(unittest.TestCase):
    def setUp(self) -> None:
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        sys.argv = self._original_argv

    @patch("collectors.UsfsCollector.download_via_url")
    def test_skips_download_over_1gb(self, mock_download: MagicMock) -> None:
        catalog_bytes = MAX_DOWNLOAD_BYTES + 1
        collector = UsfsCollector()
        folder = Path(__file__).parent / "_tmp_usfs_test"
        folder.mkdir(exist_ok=True)
        try:
            notes, total_bytes, exts = collector._process_publication_files(
                1,
                MagicMock(),
                folder,
                [("big.zip", "https://example.com/big.zip", catalog_bytes)],
            )
            mock_download.assert_not_called()
            self.assertEqual(total_bytes, catalog_bytes)
            self.assertTrue(any("Skipped download (>1GB)" in n for n in notes))
            self.assertIn("zip", exts)
        finally:
            for f in folder.iterdir():
                f.unlink(missing_ok=True)
            folder.rmdir()

    def test_pdf_names_constant(self) -> None:
        self.assertEqual(len(_PDF_NAMES), 3)


if __name__ == "__main__":
    unittest.main()
