"""Tests for FercSourcing."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.FercSourcing import FercSourcing
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

SAMPLE_ROW = {
    "url": "https://data.ferc.gov/annual-charges/oil-assessment-table",
    "title": "Oil Assessment Table",
    "summary": "Oil Annual Charges Assessment",
    "agency": "Federal Energy Regulatory Commission",
    "office": "Office of the Executive Director",
    "record_id": "2",
}


class TestFercSourcing(unittest.TestCase):
    """Tests for FERC batch sourcing."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "ferc_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "ferc.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove the temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("sourcing.FercSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced record with catalog fields."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        FercSourcing(fetcher=fetcher).run(-1)

        fetcher.close.assert_called_once()
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Oil Assessment Table")
        self.assertEqual(projects[0]["agency"], "Federal Energy Regulatory Commission")
        self.assertEqual(projects[0]["office"], "Office of the Executive Director")
        self.assertEqual(projects[0]["summary"], "Oil Annual Charges Assessment")
        self.assertEqual(
            projects[0]["source_url"],
            "https://data.ferc.gov/annual-charges/oil-assessment-table",
        )

    @patch("sourcing.FercSourcing.DuplicateChecker")
    def test_run_skips_already_sourced_urls(self, mock_checker_cls: MagicMock) -> None:
        """A stored landing page is not inserted again, including a trailing slash."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        existing_url = "https://data.ferc.gov/annual-charges/oil-assessment-table"
        self.storage.create_record(existing_url)
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [
            {**SAMPLE_ROW, "url": existing_url + "/"},
            {
                **SAMPLE_ROW,
                "url": "https://data.ferc.gov/active-hydropower-projects/active-exemptions",
                "title": "Active Exemptions",
                "record_id": "30",
            },
        ]

        FercSourcing(fetcher=fetcher).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Active Exemptions")

    @patch("sourcing.FercSourcing.DuplicateChecker")
    @patch.object(Args, "num_rows", 1)
    def test_run_respects_num_rows_on_pending_batch(
        self,
        mock_checker_cls: MagicMock,
    ) -> None:
        """num_rows caps how many pending datasets are inserted per run."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [
            SAMPLE_ROW,
            {
                **SAMPLE_ROW,
                "url": "https://data.ferc.gov/active-hydropower-projects/active-licenses",
                "title": "Active Licenses",
                "record_id": "31",
            },
        ]

        FercSourcing(fetcher=fetcher).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)


if __name__ == "__main__":
    unittest.main()
