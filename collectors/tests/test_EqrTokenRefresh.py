"""Tests for refreshing EQR zip URLs before resume."""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from collectors.EqrTokenRefresh import refresh_eqr_download_urls
from collectors.EqrZipLink import EqrZipLink
from storage import Storage
from storage.ProjectFileStore import ProjectFileRow, ProjectFileStore
from utils.Args import Args
from utils.Errors import ProjectAbort
from utils.Logger import Logger


class TestEqrTokenRefresh(unittest.TestCase):
    """A fresh viewer link replaces the stored path token."""

    def setUp(self) -> None:
        """Open a temporary database."""
        self._argv = sys.argv.copy()
        sys.argv = ["test", "noop"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self._dir = Path(tempfile.mkdtemp())
        Storage.reset()
        self.storage = Storage.initialize("StorageSQLLite", db_path=self._dir / "test.db")
        self.store = ProjectFileStore.from_storage()
        self.drpid = Storage.create_record("https://eqrreportviewer.ferc.gov/?start=2021Q1&end=2021Q4")

    def tearDown(self) -> None:
        """Close the database and remove the temp folder."""
        self.storage.close()
        Storage.reset()
        sys.argv = self._argv
        if self._dir.exists():
            shutil.rmtree(self._dir)

    def test_refresh_replaces_the_path_token(self) -> None:
        """The file name stays put and the href is updated."""
        old = "https://eqrreportviewer.ferc.gov/DownloadRepositoryProd/OLD/BulkNew/CSV/CSV_2021_Q1.zip"
        new = "https://eqrreportviewer.ferc.gov/DownloadRepositoryProd/NEW/BulkNew/CSV/CSV_2021_Q1.zip"
        self.store.replace_for_project(
            self.drpid,
            [ProjectFileRow(self.drpid, "CSV_2021_Q1.zip", 10, old, False, False)],
        )
        refresh_eqr_download_urls(
            self.drpid,
            self.store,
            lambda: [EqrZipLink("CSV_2021_Q1.zip", new, 10)],
        )
        pending = self.store.list_pending_downloads(self.drpid)
        self.assertEqual(pending[0].source_url, new)

    def test_refresh_stops_when_the_viewer_has_no_csv_links(self) -> None:
        """An empty link list does not leave the resume pointing at a dead token."""
        old = "https://eqrreportviewer.ferc.gov/DownloadRepositoryProd/OLD/BulkNew/CSV/CSV_2021_Q1.zip"
        self.store.replace_for_project(
            self.drpid,
            [ProjectFileRow(self.drpid, "CSV_2021_Q1.zip", 10, old, False, False)],
        )
        with self.assertRaises(ProjectAbort):
            refresh_eqr_download_urls(self.drpid, self.store, lambda: [])


if __name__ == "__main__":
    unittest.main()
