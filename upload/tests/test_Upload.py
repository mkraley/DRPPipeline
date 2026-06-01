"""
Unit tests for DataLumosUploader (upload module).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

from upload.DataLumosUploader import DataLumosUploader, _warn_if_num_files_mismatch
from upload.UploadIssueReporter import UploadIssueReporter


class TestDataLumosUploader(unittest.TestCase):
    """Test cases for DataLumosUploader module."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "upload"]

        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.uploader = DataLumosUploader()

    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_validate_project_missing_title(self) -> None:
        """Test validation fails when title is missing."""
        project = {"summary": "Test summary"}
        errors = self.uploader._validate_project(project)
        self.assertIn("Missing required field: title", errors)

    def test_validate_project_missing_summary(self) -> None:
        """Test validation fails when summary is missing."""
        project = {"title": "Test title"}
        errors = self.uploader._validate_project(project)
        self.assertIn("Missing required field: summary", errors)

    def test_validate_project_valid(self) -> None:
        """Test validation passes with required fields."""
        project = {"title": "Test title", "summary": "Test summary"}
        errors = self.uploader._validate_project(project)
        self.assertEqual(errors, [])

    def test_validate_project_folder_not_exists(self) -> None:
        """Test validation fails when folder_path doesn't exist."""
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": "/nonexistent/path/to/folder",
        }
        errors = self.uploader._validate_project(project)
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_validate_project_folder_exists(self) -> None:
        """Test validation passes when folder_path exists."""
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": str(self.temp_dir),
        }
        errors = self.uploader._validate_project(project)
        self.assertEqual(errors, [])

    def test_run_project_not_found(self) -> None:
        """Test run records error when project not found."""
        with patch("upload.UploadIssueReporter.record_error") as mock_record_error:
            self.uploader.run(9999)
            mock_record_error.assert_called_once()
            args = mock_record_error.call_args[0]
            self.assertEqual(args[0], 9999)
            self.assertIn("not found", args[1])

    def test_run_validation_fails(self) -> None:
        """Test run records errors when validation fails."""
        drpid = Storage.create_record("https://example.com/test")

        with patch("upload.UploadIssueReporter.record_error") as mock_record_error:
            self.uploader.run(drpid)
            self.assertTrue(mock_record_error.called)

    def test_get_field(self) -> None:
        """Test get_field returns trimmed value or empty string."""
        from utils.project_utils import get_field

        project = {"title": "  x  ", "missing": None}
        self.assertEqual(get_field(project, "title"), "x")
        self.assertEqual(get_field(project, "missing"), "")

    @patch("upload.UploadIssueReporter.record_warning")
    def test_warn_if_num_files_mismatch_records_when_differs(
        self, mock_record_warning: MagicMock
    ) -> None:
        reporter = UploadIssueReporter(42)
        _warn_if_num_files_mismatch(reporter, {"num_files": 3}, 2)
        mock_record_warning.assert_called_once()
        self.assertEqual(mock_record_warning.call_args[0][0], 42)
        msg = mock_record_warning.call_args[0][1]
        self.assertIn("Upload batch count (2)", msg)
        self.assertIn("num_files from collection (3)", msg)

    @patch("upload.UploadIssueReporter.record_warning")
    def test_warn_if_num_files_mismatch_skips_when_match(
        self, mock_record_warning: MagicMock
    ) -> None:
        reporter = UploadIssueReporter(1)
        _warn_if_num_files_mismatch(reporter, {"num_files": 2}, 2)
        mock_record_warning.assert_not_called()

    @patch("upload.UploadIssueReporter.record_warning")
    def test_warn_if_num_files_skips_when_num_files_null(
        self, mock_record_warning: MagicMock
    ) -> None:
        reporter = UploadIssueReporter(1)
        _warn_if_num_files_mismatch(reporter, {}, 2)
        mock_record_warning.assert_not_called()

    def test_warn_if_num_files_mismatch_persists_to_storage(self) -> None:
        drpid = Storage.create_record("https://example.com/test")
        Storage.update_record(drpid, {"num_files": 5})
        reporter = UploadIssueReporter(drpid)
        _warn_if_num_files_mismatch(reporter, Storage.get(drpid), 3)
        record = Storage.get(drpid)
        self.assertIsNotNone(record)
        assert record is not None
        self.assertIn("Upload batch count (3)", record.get("warnings") or "")

    @patch("upload.DataLumosUploader.Storage")
    @patch.object(DataLumosUploader, "_upload_project", return_value="12345")
    def test_run_sets_uploaded_status(
        self,
        mock_upload_project: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.get.return_value = {
            "title": "T",
            "summary": "S",
            "status": "collected",
            "source_url": "",
        }
        uploader = DataLumosUploader()
        uploader._session = MagicMock()
        uploader.run(7)
        mock_upload_project.assert_called_once()
        call_args = mock_upload_project.call_args[0]
        self.assertEqual(call_args[1], 7)
        self.assertIsInstance(call_args[2], UploadIssueReporter)
        mock_storage.update_record.assert_called_with(
            7,
            {"datalumos_id": "12345", "status": "uploaded"},
        )

    @patch("upload.DataLumosUploader.Storage")
    @patch.object(DataLumosUploader, "_upload_project", return_value="12345")
    def test_run_sets_uploaded_large_file_status(
        self,
        mock_upload_project: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.get.return_value = {
            "title": "T",
            "summary": "S",
            "status": "collected - large file",
            "source_url": "",
        }
        uploader = DataLumosUploader()
        uploader._session = MagicMock()
        uploader.run(7)
        mock_storage.update_record.assert_called_with(
            7,
            {"datalumos_id": "12345", "status": "uploaded - large file"},
        )


class TestDataLumosUploaderValidation(unittest.TestCase):
    """Additional validation tests."""

    def setUp(self) -> None:
        """Set up test environment."""
        sys.argv = ["test", "upload"]
        Args._initialized = False
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        self.uploader = DataLumosUploader()
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        """Clean up after tests."""
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_validate_project_folder_is_file(self) -> None:
        """Test validation fails when folder_path is a file, not directory."""
        test_file = self.temp_dir / "test_file.txt"
        test_file.write_text("test")

        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": str(test_file),
        }
        errors = self.uploader._validate_project(project)
        self.assertTrue(any("not a directory" in e for e in errors))

    def test_validate_project_empty_strings_treated_as_missing(self) -> None:
        """Test that empty strings are treated as missing values."""
        project = {"title": "", "summary": ""}
        errors = self.uploader._validate_project(project)
        self.assertIn("Missing required field: title", errors)
        self.assertIn("Missing required field: summary", errors)


if __name__ == "__main__":
    unittest.main()
