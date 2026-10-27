"""Tests for EpaSourcing wiring onto shared DataGov modules."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sourcing.EpaSourcing import AGENCY, DEFAULT_ORG_SLUG, EpaSourcing
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

SAMPLE_ROW = {
    "url": "https://catalog.data.gov/dataset/air-quality",
    "title": "Air Quality",
    "agency": AGENCY,
    "office": AGENCY,
    "record_id": "air-quality",
    "identifier": "US-GOV-EPA-1",
}


class TestEpaSourcing(unittest.TestCase):
    """Tests for EPA Data.gov sourcing."""

    def setUp(self) -> None:
        """Create isolated Storage and Args for each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "epa_sourcing"]
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

    def test_default_org_slug_is_epa(self) -> None:
        """EPA defaults to the Data.gov epa organization."""
        self.assertEqual(DEFAULT_ORG_SLUG, "epa")

    @patch("sourcing.DataGovSourcing.DuplicateChecker")
    def test_run_inserts_sourced_row(self, mock_checker_cls: MagicMock) -> None:
        """run(-1) creates a sourced EPA catalog record."""
        mock_checker_cls.return_value.exists_in_storage.return_value = False
        fetcher = MagicMock()
        fetcher.list_dataset_rows.return_value = [dict(SAMPLE_ROW)]

        EpaSourcing(fetcher=fetcher).run(-1)

        fetcher.close.assert_called_once()
        projects = self.storage.list_eligible_projects("sourced", None)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["agency"], AGENCY)
        self.assertEqual(
            projects[0]["source_url"],
            "https://catalog.data.gov/dataset/air-quality",
        )


if __name__ == "__main__":
    unittest.main()
