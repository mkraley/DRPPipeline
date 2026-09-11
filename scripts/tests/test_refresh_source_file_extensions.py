"""
Unit tests for refresh_source_file_extensions helpers.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from collectors.BtsMetadataExtractor import BtsDownloadFile
from scripts.refresh_source_file_extensions import (
    STATUS_UPDATED_INVENTORY,
    extensions_from_download_files,
    extensions_from_source_html,
    refresh_project,
)
from utils.Args import Args
from utils.Logger import Logger

_FIXTURE = (
    REPO_ROOT
    / "collectors"
    / "tests"
    / "fixtures"
    / "bts_detail_54854.html"
)


class TestRefreshSourceFileExtensions(unittest.TestCase):
    """Tests for top-level extension survey helpers."""

    def test_extensions_from_download_files(self) -> None:
        """Extensions come from filenames, not archive members."""
        files = [
            BtsDownloadFile(
                label="main",
                url="https://example.com/a.zip",
                filename="a.zip",
                size_bytes=1,
                is_main=True,
            ),
            BtsDownloadFile(
                label="doc",
                url="https://example.com/b.PDF",
                filename="b.PDF",
                size_bytes=1,
                is_main=False,
            ),
        ]
        self.assertEqual(extensions_from_download_files(files), "pdf, zip")

    def test_extensions_from_source_html_fixture(self) -> None:
        """Fixture detail page yields top-level catalog extensions only."""
        html = _FIXTURE.read_text(encoding="utf-8")
        url = "https://rosap.ntl.bts.gov/view/dot/54854"
        result = extensions_from_source_html(html, url)
        self.assertTrue(result)
        self.assertNotIn("shp", result)
        for token in result.split(", "):
            self.assertTrue(token)
            self.assertFalse(token.startswith("."))

    def test_refresh_project_dry_run_does_not_write(self) -> None:
        """Dry-run surveys without Storage or sheet updates."""
        project = {
            "DRPID": 9,
            "status": STATUS_UPDATED_INVENTORY,
            "source_url": "https://rosap.ntl.bts.gov/view/dot/54854",
            "extensions": "shp, zip",
        }
        downloader = MagicMock()
        downloader.fetch_page_html.return_value = (
            200,
            _FIXTURE.read_text(encoding="utf-8"),
            None,
            False,
        )
        with patch(
            "scripts.refresh_source_file_extensions.get_inventory_sheet_updater"
        ) as mock_updater:
            ok = refresh_project(
                project, downloader, dry_run=True, update_sheet=True
            )
        self.assertTrue(ok)
        mock_updater.assert_not_called()


class TestUpdateFileExtensionsSheet(unittest.TestCase):
    """Tests for inventory updater file-extensions-only writes."""

    def setUp(self) -> None:
        """Initialize Args for sheet updater construction."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "publisher"]
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

    def tearDown(self) -> None:
        """Restore argv."""
        sys.argv = self._original_argv
        Args._initialized = False

    def test_baserow_formats_extensions(self) -> None:
        """Baserow updater uppercases and CSV-formats extensions."""
        from publisher.BaserowBatchSheetUpdater import BaserowBatchSheetUpdater

        updater = BaserowBatchSheetUpdater()
        self.assertEqual(updater._file_extensions_column(), "File extensions")
        self.assertEqual(
            updater._format_file_extensions_for_sheet("csv, zip"),
            "CSV,ZIP",
        )

    def test_data_inventories_passthrough(self) -> None:
        """Data inventories updater keeps the longer column name."""
        from publisher.GoogleSheetUpdater import GoogleSheetUpdater

        updater = GoogleSheetUpdater()
        self.assertEqual(
            updater._file_extensions_column(),
            "File extensions of data uploads",
        )
        self.assertEqual(
            updater._format_file_extensions_for_sheet("csv, zip"),
            "csv, zip",
        )


if __name__ == "__main__":
    unittest.main()
