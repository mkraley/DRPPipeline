"""Tests for BtsSourcing orchestrator module."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.BtsSourcing import BtsSourcing
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

SAMPLE_ROW = {
    "url": "https://rosap.ntl.bts.gov/view/dot/92758",
    "title": "Example Dataset",
    "agency": "Department of Transportation",
    "office": "Bureau of Transportation Statistics",
    "record_id": "92758",
}


class TestBtsSourcing(unittest.TestCase):
    """Tests for BTS batch sourcing module."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "bts_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "bts.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("sourcing.BtsSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced record with metadata fields."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        BtsSourcing(fetcher=fetcher).run(-1)

        fetcher.close.assert_called_once()
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Example Dataset")
        self.assertEqual(projects[0]["agency"], "Department of Transportation")
        self.assertEqual(projects[0]["office"], "Bureau of Transportation Statistics")
        self.assertIsNone(projects[0].get("summary"))
        self.assertIsNone(projects[0].get("num_files"))
        self.assertIsNone(projects[0].get("file_size"))

    @patch("sourcing.BtsSourcing.DuplicateChecker")
    def test_run_skips_duplicate_urls(self, mock_checker_cls: MagicMock) -> None:
        """Duplicate URLs do not create a second row."""
        mock_checker_cls.return_value.exists_in_storage.return_value = True
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        BtsSourcing(fetcher=fetcher).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 0)

    @patch("sourcing.BtsSourcing.DuplicateChecker")
    def test_run_skips_already_sourced_record_ids(self, mock_checker_cls: MagicMock) -> None:
        """Pending batch skips record IDs already present in Storage URLs."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        existing_url = "https://rosap.ntl.bts.gov/view/dot/100"
        self.storage.create_record(existing_url)
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [
            {**SAMPLE_ROW, "url": existing_url, "record_id": "100"},
            {**SAMPLE_ROW, "url": "https://rosap.ntl.bts.gov/view/dot/200", "record_id": "200"},
        ]

        BtsSourcing(fetcher=fetcher).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["source_url"], "https://rosap.ntl.bts.gov/view/dot/200")

    @patch("sourcing.BtsSourcing.DuplicateChecker")
    @patch.object(Args, "num_rows", 1)
    def test_run_respects_num_rows_on_pending_batch(
        self,
        mock_checker_cls: MagicMock,
    ) -> None:
        """num_rows caps how many pending datasets are inserted per run."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [
            {**SAMPLE_ROW, "url": "https://rosap.ntl.bts.gov/view/dot/1", "record_id": "1"},
            {**SAMPLE_ROW, "url": "https://rosap.ntl.bts.gov/view/dot/2", "record_id": "2"},
        ]

        BtsSourcing(fetcher=fetcher).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)


if __name__ == "__main__":
    unittest.main()
