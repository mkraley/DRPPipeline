"""Tests for collecting one AirData column."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from collectors.AqsCollector import AqsCollector
from sourcing.AqsPageParser import AqsPageParser
from storage import Storage
from utils.Args import Args
from utils.Errors import ProjectAbort
from utils.Logger import Logger

_PAGE = """
<h2>Daily AQI</h2>
<table>
<tr><th>Year</th><th>Daily AQI by CBSA</th></tr>
<tr><td>2024</td><td><a href="daily_aqi_by_cbsa_2024.zip">f</a><br>3 Rows<br>4 KB</td></tr>
</table>
"""
_BODY = b"aqs-zip"
_PDF = b"%PDF-1.4 format"


class TestAqsCollector(unittest.TestCase):
    """One column saves its zip and the format page."""

    def setUp(self) -> None:
        """Point collection at a temporary database and folder."""
        self._argv = sys.argv.copy()
        sys.argv = ["test", "collect"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        Args._config["base_output_dir"] = str(self.temp_dir)
        Args._config["google_sheet_name"] = "AQS"
        (self.temp_dir / "AirData FileFormats.pdf").write_bytes(_PDF)
        Storage.reset()
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.temp_dir / "aqs.db")

    def tearDown(self) -> None:
        """Close the database and remove the temp folder."""
        self.storage.close()
        Storage.reset()
        sys.argv = self._argv
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_collect_saves_the_format_page_before_the_zip(self) -> None:
        """The column zip and the shared format PDF land in the project folder."""
        url = "https://aqs.epa.gov/aqsweb/airdata/download_files.html#daily_aqi_by_cbsa"
        drpid = self.storage.create_record(url)
        collector = self._collector()

        result = collector._collect(url, drpid, {})

        folder = self.temp_dir / f"AQS{drpid:06d}"
        self.assertFalse((folder / "FileFormats.html").exists())
        self.assertFalse((folder / "FileFormats.zip").exists())
        self.assertEqual((folder / "AirData FileFormats.pdf").read_bytes(), _PDF)
        self.assertEqual((folder / "daily_aqi_by_cbsa_2024.zip").read_bytes(), _BODY)
        self.assertIn("AirData FileFormats.pdf", result["summary"])
        self.assertEqual(result["title"], "Air Data Daily AQI by CBSA")
        self.assertEqual(result["office"], "Environmental Protection Agency")
        self.assertNotIn("status", result)

    def test_unknown_column_aborts(self) -> None:
        """A fragment that is not on the page stops the project."""
        url = "https://aqs.epa.gov/aqsweb/airdata/download_files.html#missing"
        drpid = self.storage.create_record(url)
        with self.assertRaises(ProjectAbort):
            self._collector()._collect(url, drpid, {})

    def _collector(self) -> AqsCollector:
        """Return a collector bound to the fixture page and a fake download."""
        client = MagicMock()
        client.fetch_html.return_value = _PAGE
        return AqsCollector(
            parser=AqsPageParser(),
            client=client,
            download_file=_save_body,
            content_length=lambda _url: len(_BODY),
        )


def _save_body(_url: str, dest: Path) -> tuple[int, bool]:
    """Write the fixture body."""
    dest.write_bytes(_BODY)
    return len(_BODY), True


if __name__ == "__main__":
    unittest.main()
