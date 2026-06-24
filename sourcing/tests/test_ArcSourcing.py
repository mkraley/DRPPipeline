"""Tests for ArcSourcing orchestrator module."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

from sourcing.ArcSourcing import ArcSourcing

SAMPLE_ROW = {
    "url": "https://agdatacommons.nal.usda.gov/articles/dataset/Example/1",
    "title": "Example",
    "agency": "US Department of Agriculture",
    "office": "National Agricultural Library",
    "num_files": "1",
    "file_size": "1.0 KB",
    "extensions": "csv",
}


class TestArcSourcing(unittest.TestCase):
    """Tests for ARC batch sourcing module."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "arc_sourcing"]
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize(
            "StorageSQLLite",
            db_path=self.temp_dir / "arc.db",
        )

    def tearDown(self) -> None:
        """Restore argv and remove temp database."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    @patch("sourcing.ArcSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced record with inventory fields."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [1]
        fetcher.fetch_article.return_value = {"id": 1}
        fetcher.build_candidate_row.return_value = dict(SAMPLE_ROW)

        ArcSourcing(fetcher=fetcher, request_delay=0).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Example")
        self.assertEqual(projects[0]["num_files"], 1)
        self.assertFalse(projects[0].get("status_notes"))

    @patch("sourcing.ArcSourcing.DuplicateChecker")
    def test_run_skips_duplicate_urls(self, mock_checker_cls: MagicMock) -> None:
        """Duplicate URLs do not create a second row."""
        mock_checker_cls.return_value.exists_in_storage.return_value = True
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [1]
        fetcher.fetch_article.return_value = {"id": 1}
        fetcher.build_candidate_row.return_value = dict(SAMPLE_ROW)

        ArcSourcing(fetcher=fetcher, request_delay=0).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 0)
