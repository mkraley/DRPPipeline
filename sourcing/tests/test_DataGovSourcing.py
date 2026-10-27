"""Tests for shared DataGovSourcing orchestrator module."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.DataGovSourcing import DataGovSourcing
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

SAMPLE_ROW = {
    "url": "https://catalog.data.gov/dataset/air-quality",
    "title": "Air Quality",
    "agency": "Environmental Protection Agency",
    "office": "Environmental Protection Agency",
    "record_id": "air-quality",
    "identifier": "US-GOV-EPA-1",
}


class TestDataGovSourcing(unittest.TestCase):
    """Tests for Data.gov batch sourcing module."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "datagov_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "epa.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def _run(self, fetcher: MagicMock) -> None:
        """Run DataGovSourcing with an EPA label."""
        DataGovSourcing(fetcher=fetcher, source_label="EPA").run(-1)

    @patch("sourcing.DataGovSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced record with metadata fields."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        self._run(fetcher)

        fetcher.close.assert_called_once()
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Air Quality")
        self.assertEqual(
            projects[0]["agency"],
            "Environmental Protection Agency",
        )
        self.assertEqual(
            projects[0]["source_url"],
            "https://catalog.data.gov/dataset/air-quality",
        )

    @patch("sourcing.DataGovSourcing.DuplicateChecker")
    def test_run_skips_already_sourced_slugs(self, mock_checker_cls: MagicMock) -> None:
        """Pending batch skips catalog slugs already present in Storage URLs."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        existing_url = "https://catalog.data.gov/dataset/keep-me"
        self.storage.create_record(existing_url)
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [
            {**SAMPLE_ROW, "url": existing_url, "record_id": "keep-me"},
            {
                **SAMPLE_ROW,
                "url": "https://catalog.data.gov/dataset/year-2025",
                "record_id": "year-2025",
            },
        ]

        self._run(fetcher)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(
            projects[0]["source_url"],
            "https://catalog.data.gov/dataset/year-2025",
        )

    @patch("sourcing.DataGovSourcing.DuplicateChecker")
    @patch.object(Args, "num_rows", 1)
    def test_run_respects_num_rows_on_pending_batch(
        self,
        mock_checker_cls: MagicMock,
    ) -> None:
        """num_rows caps how many pending datasets are inserted per run."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [
            {
                **SAMPLE_ROW,
                "url": "https://catalog.data.gov/dataset/a",
                "record_id": "a",
            },
            {
                **SAMPLE_ROW,
                "url": "https://catalog.data.gov/dataset/b",
                "record_id": "b",
            },
        ]

        self._run(fetcher)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)


if __name__ == "__main__":
    unittest.main()
