"""
Unit tests for DuplicateChecker.
"""

import tempfile
import unittest
from pathlib import Path

from utils.Args import Args
from utils.Logger import Logger
from storage import Storage
from duplicate_checking import DuplicateChecker


class TestDuplicateChecker(unittest.TestCase):
    """Test cases for DuplicateChecker class."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        import sys
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]

        Args.initialize()
        Logger.initialize(log_level="WARNING")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.checker = DuplicateChecker(self.storage)

    def tearDown(self) -> None:
        """Clean up after each test."""
        import sys
        self.storage.close()
        sys.argv = self._original_argv
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_exists_in_storage_returns_false_when_not_present(self) -> None:
        """Test exists_in_storage returns False when URL is not in database."""
        self.assertFalse(self.checker.exists_in_storage("https://example.com"))

    def test_exists_in_storage_returns_false_when_other_urls_exist(self) -> None:
        """Test exists_in_storage returns False when other URLs exist but not the one checked."""
        self.storage.create_record("https://existing.com")
        self.assertFalse(self.checker.exists_in_storage("https://other.com"))

    def test_exists_in_storage_returns_true_when_present(self) -> None:
        """Test exists_in_storage returns True when URL already exists in database."""
        self.storage.create_record("https://example.com")
        self.assertTrue(self.checker.exists_in_storage("https://example.com"))
