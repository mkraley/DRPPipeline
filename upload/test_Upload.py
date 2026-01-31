"""
Unit tests for Upload module.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

from upload.Upload import Upload


class TestUpload(unittest.TestCase):
    """Test cases for Upload module."""

    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test", "upload"]

        # Reset Args singleton state for fresh initialization
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        Args.initialize()
        Logger.initialize(log_level="WARNING")

        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
        self.storage = Storage.initialize("StorageSQLLite", db_path=self.test_db_path)
        self.upload = Upload()

    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        self.storage.close()
        Storage.reset()  # Reset singleton for next test
        # Reset Args singleton for next test
        Args._initialized = False
        Args._config = {}
        Args._parsed_args = {}
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_validate_project_missing_title(self) -> None:
        """Test validation fails when title is missing."""
        project = {"summary": "Test summary"}
        errors = self.upload._validate_project(project)
        self.assertIn("Missing required field: title", errors)

    def test_validate_project_missing_summary(self) -> None:
        """Test validation fails when summary is missing."""
        project = {"title": "Test title"}
        errors = self.upload._validate_project(project)
        self.assertIn("Missing required field: summary", errors)

    def test_validate_project_valid(self) -> None:
        """Test validation passes with required fields."""
        project = {"title": "Test title", "summary": "Test summary"}
        errors = self.upload._validate_project(project)
        self.assertEqual(errors, [])

    def test_validate_project_folder_not_exists(self) -> None:
        """Test validation fails when folder_path doesn't exist."""
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": "/nonexistent/path/to/folder",
        }
        errors = self.upload._validate_project(project)
        self.assertTrue(any("does not exist" in e for e in errors))

    def test_validate_project_folder_exists(self) -> None:
        """Test validation passes when folder_path exists."""
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": str(self.temp_dir),
        }
        errors = self.upload._validate_project(project)
        self.assertEqual(errors, [])

    def test_run_project_not_found(self) -> None:
        """Test run records error when project not found."""
        with patch("upload.Upload.record_error") as mock_record_error:
            self.upload.run(9999)  # Non-existent DRPID
            mock_record_error.assert_called_once()
            args = mock_record_error.call_args[0]
            self.assertEqual(args[0], 9999)
            self.assertIn("not found", args[1])

    def test_run_validation_fails(self) -> None:
        """Test run records errors when validation fails."""
        # Create a project without required fields
        drpid = Storage.create_record("https://example.com/test")
        
        with patch("upload.Upload.record_error") as mock_record_error:
            self.upload.run(drpid)
            # Should record errors for missing title and summary
            self.assertTrue(mock_record_error.called)


class TestUploadValidation(unittest.TestCase):
    """Additional validation tests for Upload module."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.upload = Upload()
        self.temp_dir = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        """Clean up after tests."""
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)

    def test_validate_project_folder_is_file(self) -> None:
        """Test validation fails when folder_path is a file, not directory."""
        # Create a file instead of directory
        test_file = self.temp_dir / "test_file.txt"
        test_file.write_text("test")
        
        project = {
            "title": "Test title",
            "summary": "Test summary",
            "folder_path": str(test_file),
        }
        errors = self.upload._validate_project(project)
        self.assertTrue(any("not a directory" in e for e in errors))

    def test_validate_project_empty_strings_treated_as_missing(self) -> None:
        """Test that empty strings are treated as missing values."""
        project = {"title": "", "summary": ""}
        errors = self.upload._validate_project(project)
        self.assertIn("Missing required field: title", errors)
        self.assertIn("Missing required field: summary", errors)


if __name__ == "__main__":
    unittest.main()
