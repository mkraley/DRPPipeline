"""Tests for inserting EQR projects."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from collectors.EqrProjectRange import project_ranges
from sourcing.EqrProjects import insert_missing_eqr_projects
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


class TestEqrProjects(unittest.TestCase):
    """EQR spans are inserted once."""

    def setUp(self) -> None:
        """Open a temporary database."""
        self._argv = sys.argv.copy()
        sys.argv = ["test", "source"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self._dir = Path(tempfile.mkdtemp())
        Storage.reset()
        self.storage = Storage.initialize("StorageSQLLite", db_path=self._dir / "test.db")

    def tearDown(self) -> None:
        """Close the database and remove the temp folder."""
        self.storage.close()
        Storage.reset()
        sys.argv = self._argv
        if self._dir.exists():
            shutil.rmtree(self._dir)

    def test_insert_is_idempotent_and_sets_metadata(self) -> None:
        """Seven sourced rows are created, and a second call adds none."""
        first = insert_missing_eqr_projects()
        second = insert_missing_eqr_projects()
        self.assertEqual(len(first), 7)
        self.assertEqual(second, [])
        record = Storage.get(first[0])
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["status"], "sourced")
        self.assertEqual(record["next_step"], "collect")
        self.assertEqual(record["source_url"], project_ranges()[0].source_url())
        self.assertEqual(record["time_start"], "2013-07-01")
        self.assertIn("Electric Quarterly Report", record["keywords"])
        self.assertEqual(record["agency"], "Federal Energy Regulatory Commission")


if __name__ == "__main__":
    unittest.main()
