"""
Unit tests for file_utils module.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from utils.Args import Args
from utils.Logger import Logger
from utils import file_utils


class TestFileUtils(unittest.TestCase):
    """Test cases for file_utils module."""
    
    def setUp(self) -> None:
        """Set up test environment before each test."""
        self._original_argv = sys.argv.copy()
        sys.argv = ["test"]
        
        Args.initialize()
        Logger.initialize(log_level="WARNING")
        
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        sys.argv = self._original_argv
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def test_sanitize_filename_simple(self) -> None:
        """Test sanitize_filename with simple name."""
        result = file_utils.sanitize_filename("test_file")
        self.assertEqual(result, "test_file")
    
    def test_sanitize_filename_with_invalid_chars(self) -> None:
        """Test sanitize_filename removes invalid Windows characters."""
        result = file_utils.sanitize_filename("test<file>name")
        self.assertEqual(result, "test_file_name")
    
    def test_sanitize_filename_with_unicode(self) -> None:
        """Test sanitize_filename handles Unicode characters."""
        result = file_utils.sanitize_filename("test–file—name")
        self.assertEqual(result, "test-file-name")
    
    def test_sanitize_filename_empty(self) -> None:
        """Test sanitize_filename with empty string."""
        result = file_utils.sanitize_filename("")
        self.assertEqual(result, "Untitled")
    
    def test_sanitize_filename_truncates_long(self) -> None:
        """Test sanitize_filename truncates very long names."""
        long_name = "a" * 200
        result = file_utils.sanitize_filename(long_name, max_length=50)
        self.assertLessEqual(len(result), 50)
    
    def test_sanitize_filename_removes_leading_trailing_dots(self) -> None:
        """Test sanitize_filename removes leading/trailing dots."""
        result = file_utils.sanitize_filename("...test...")
        self.assertEqual(result, "test")
    
    def test_create_output_folder(self) -> None:
        """Test create_output_folder creates folder."""
        folder_path = file_utils.create_output_folder(self.temp_dir, 123)
        
        self.assertIsNotNone(folder_path)
        self.assertTrue(folder_path.exists())
        self.assertEqual(folder_path.name, "DRP000123")
    
    def test_create_output_folder_multiple(self) -> None:
        """Test create_output_folder creates multiple folders."""
        folder1 = file_utils.create_output_folder(self.temp_dir, 1)
        folder2 = file_utils.create_output_folder(self.temp_dir, 2)
        
        self.assertNotEqual(folder1, folder2)
        self.assertTrue(folder1.exists())
        self.assertTrue(folder2.exists())
