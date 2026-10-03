"""Tests for project_files persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage import Storage
from storage.ProjectFileStore import ProjectFileRow, ProjectFileStore
from utils.Args import Args
from utils.Logger import Logger


class TestProjectFileStore(unittest.TestCase):
    """project_files rows are replaced per project."""

    def setUp(self) -> None:
        """Open a temporary database."""
        import sys

        self._argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self._dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize("StorageSQLLite", db_path=self._dir / "test.db")
        self.store = ProjectFileStore.from_storage()

    def tearDown(self) -> None:
        """Close the database and restore argv."""
        import shutil
        import sys

        self.storage.close()
        Storage.reset()
        sys.argv = self._argv
        if self._dir.exists():
            shutil.rmtree(self._dir)

    def test_replace_and_list_pending(self) -> None:
        """Downloaded and pending rows round-trip."""
        self.store.replace_for_project(
            7,
            [
                ProjectFileRow(7, "a.bin", 10, "https://example.com/a", True, False),
                ProjectFileRow(7, "sub/b.bin", 20, "https://example.com/b", False, False),
            ],
        )
        pending = self.store.list_pending_downloads(7)
        self.assertEqual([row.relative_path for row in pending], ["sub/b.bin"])
        self.store.mark_downloaded(7, "sub/b.bin", 20)
        self.store.mark_uploaded(7, ["a.bin"])
        rows = self.store.list_for_project(7)
        uploaded = {row.relative_path: row.uploaded for row in rows}
        self.assertEqual(uploaded["a.bin"], True)
        self.assertTrue(all(row.downloaded for row in rows))
        self.assertEqual(self.store.list_pending_uploads(7)[0].relative_path, "sub/b.bin")
