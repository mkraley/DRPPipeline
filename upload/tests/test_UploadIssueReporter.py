"""Tests for UploadIssueReporter."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger
from upload.UploadIssueReporter import UploadIssueReporter


class TestUploadIssueReporter(unittest.TestCase):
    def setUp(self) -> None:
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "upload"]
        Args._initialized = False
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.temp_dir / "test.db")

    def tearDown(self) -> None:
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()

    def test_warn_persists_to_storage(self) -> None:
        drpid = Storage.create_record("https://example.com/test")
        UploadIssueReporter(drpid).warn("Upload form: keyword missing")
        record = Storage.get(drpid)
        assert record is not None
        self.assertIn("Upload form: keyword missing", record.get("warnings") or "")

    @patch("upload.UploadIssueReporter.record_error")
    def test_error_delegates_to_record_error(self, mock_record_error) -> None:
        UploadIssueReporter(9).error("Upload failed: timeout")
        mock_record_error.assert_called_once_with(9, "Upload failed: timeout")


if __name__ == "__main__":
    unittest.main()
