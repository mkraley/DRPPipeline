"""Tests for AdcSourcing orchestrator module."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

from sourcing.AdcSourcing import AdcSourcing

SAMPLE_ROW = {
    "url": "https://agdatacommons.nal.usda.gov/articles/dataset/Example/1",
    "title": "Example",
    "agency": "US Department of Agriculture",
    "office": "National Agricultural Library",
    "num_files": "1",
    "file_size": "1.0 KB",
    "extensions": "csv",
}


class TestAdcSourcing(unittest.TestCase):
    """Tests for ADC batch sourcing module."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "adc_sourcing"]
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

    @patch("sourcing.AdcSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced record with inventory fields."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [1]
        fetcher.fetch_article.return_value = {"id": 1}
        fetcher.build_candidate_row.return_value = dict(SAMPLE_ROW)

        AdcSourcing(fetcher=fetcher, request_delay=0).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["title"], "Example")
        self.assertEqual(projects[0]["num_files"], 1)
        self.assertFalse(projects[0].get("status_notes"))

    @patch("sourcing.AdcSourcing.DuplicateChecker")
    def test_run_skips_duplicate_urls(self, mock_checker_cls: MagicMock) -> None:
        """Duplicate URLs do not create a second row."""
        mock_checker_cls.return_value.exists_in_storage.return_value = True
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [1]
        fetcher.fetch_article.return_value = {"id": 1}
        fetcher.build_candidate_row.return_value = dict(SAMPLE_ROW)

        AdcSourcing(fetcher=fetcher, request_delay=0).run(-1)

        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 0)

    @patch("sourcing.AdcSourcing.DuplicateChecker")
    def test_run_skips_already_sourced_article_ids(self, mock_checker_cls: MagicMock) -> None:
        """Pending batch skips article IDs already present in Storage URLs."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        existing_url = (
            "https://agdatacommons.nal.usda.gov/articles/dataset/Existing/100"
        )
        self.storage.create_record(existing_url)
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [100, 200]
        fetcher.fetch_article.return_value = {"id": 200}
        fetcher.build_candidate_row.return_value = {
            **SAMPLE_ROW,
            "url": (
                "https://agdatacommons.nal.usda.gov/articles/dataset/New/200"
            ),
        }

        AdcSourcing(fetcher=fetcher, request_delay=0).run(-1)

        fetcher.fetch_article.assert_called_once_with(200)
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)

    @patch("sourcing.AdcSourcing.DuplicateChecker")
    @patch.object(Args, "num_rows", 2)
    def test_run_respects_num_rows_on_pending_batch(
        self,
        mock_checker_cls: MagicMock,
    ) -> None:
        """num_rows caps how many pending articles are fetched per run."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [1, 2, 3, 4]
        fetcher.fetch_article.side_effect = [
            {"id": 1},
            {"id": 2},
        ]
        fetcher.build_candidate_row.side_effect = [
            {**SAMPLE_ROW, "url": f"https://agdatacommons.nal.usda.gov/articles/dataset/X/{index}"}
            for index in (1, 2)
        ]

        AdcSourcing(fetcher=fetcher, request_delay=0).run(-1)

        self.assertEqual(fetcher.fetch_article.call_count, 2)
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 2)

    @patch("sourcing.AdcSourcing.DuplicateChecker")
    @patch("sourcing.AdcSourcing.time.sleep")
    def test_fetch_article_retries_403(
        self,
        mock_sleep: MagicMock,
        mock_checker_cls: MagicMock,
    ) -> None:
        """HTTP 403 responses are retried before failing."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_article_ids.return_value = [42]
        forbidden = requests.HTTPError("403 Client Error: Forbidden")
        forbidden.response = MagicMock(status_code=403)
        fetcher.fetch_article.side_effect = [forbidden, {"id": 42}]
        fetcher.build_candidate_row.return_value = {
            **SAMPLE_ROW,
            "url": "https://agdatacommons.nal.usda.gov/articles/dataset/X/42",
        }

        AdcSourcing(
            fetcher=fetcher,
            request_delay=0,
            forbidden_retries=1,
            forbidden_backoff=0.0,
        ).run(-1)

        self.assertEqual(fetcher.fetch_article.call_count, 2)
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
