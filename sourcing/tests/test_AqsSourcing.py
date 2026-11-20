"""Tests for AqsSourcing."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.AqsSourcing import AqsSourcing
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

_PAGE = """
<h2>Daily Summary Data</h2>
<table>
<tr><th>Year</th><th>Ozone (44201)</th><th>SO2 (42401)</th></tr>
<tr>
<td>2024</td>
<td><a href="daily_44201_2024.zip">f</a><br>8 Rows<br>9 KB</td>
<td><a href="daily_42401_2024.zip">f</a><br>4 Rows<br>5 KB</td>
</tr>
</table>
"""


class TestAqsSourcing(unittest.TestCase):
    """Tests for AirData column sourcing."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "aqs_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "aqs.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove the temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _sourcing(self) -> AqsSourcing:
        """Return sourcing bound to the fixture page."""
        client = MagicMock()
        client.fetch_html.return_value = _PAGE
        return AqsSourcing(client=client)

    @patch("sourcing.AqsSourcing.DuplicateChecker")
    def test_run_inserts_one_project_per_column(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced project for each column."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False

        self._sourcing().run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        titles = [project["title"] for project in projects]
        self.assertEqual(
            titles,
            [
                "Daily Summary Data - Ozone (44201)",
                "Daily Summary Data - SO2 (42401)",
            ],
        )
        self.assertEqual(projects[0]["agency"], "Environmental Protection Agency")
        self.assertTrue(projects[0]["source_url"].endswith("#daily_44201"))

    @patch("sourcing.AqsSourcing.DuplicateChecker")
    def test_run_skips_urls_already_stored(self, mock_checker_cls: MagicMock) -> None:
        """A column whose URL is already stored is not inserted again."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        self.storage.create_record(
            "https://aqs.epa.gov/aqsweb/airdata/download_files.html#daily_44201"
        )

        self._sourcing().run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Daily Summary Data - SO2 (42401)")

    @patch("sourcing.AqsSourcing.DuplicateChecker")
    @patch.object(Args, "num_rows", 1)
    def test_run_respects_num_rows(self, mock_checker_cls: MagicMock) -> None:
        """num_rows caps how many columns are inserted per run."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False

        self._sourcing().run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)


if __name__ == "__main__":
    unittest.main()
