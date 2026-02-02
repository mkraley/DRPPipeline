"""
Unit tests for DataLumosFileUploader.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from utils.Logger import Logger

from upload.DataLumosFileUploader import DataLumosFileUploader


class TestDataLumosFileUploader(unittest.TestCase):
    """Test cases for DataLumosFileUploader."""

    @classmethod
    def setUpClass(cls) -> None:
        """Initialize Logger once for all tests."""
        Logger.initialize(log_level="WARNING")

    def test_init(self) -> None:
        """Test file uploader initialization."""
        mock_page = MagicMock()
        uploader = DataLumosFileUploader(mock_page, timeout=5000)
        self.assertEqual(uploader._page, mock_page)
        self.assertEqual(uploader._timeout, 5000)

    def test_get_file_paths_returns_files(self) -> None:
        """Test get_file_paths returns only files, not subdirs."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("a")
            (Path(tmp) / "b.csv").write_text("b")
            Path(tmp).joinpath("sub").mkdir()
            (Path(tmp) / "sub" / "c.txt").write_text("c")
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            paths = uploader.get_file_paths(tmp)
            names = {p.name for p in paths}
            self.assertEqual(names, {"a.txt", "b.csv"})

    def test_get_file_paths_empty_folder(self) -> None:
        """Test get_file_paths returns empty list for empty folder."""
        with tempfile.TemporaryDirectory() as tmp:
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            paths = uploader.get_file_paths(tmp)
            self.assertEqual(paths, [])

    def test_get_file_paths_missing_folder_raises(self) -> None:
        """Test get_file_paths raises FileNotFoundError for missing path."""
        mock_page = MagicMock()
        uploader = DataLumosFileUploader(mock_page)
        with self.assertRaises(FileNotFoundError):
            uploader.get_file_paths("/nonexistent/folder")

    def test_get_file_paths_not_directory_raises(self) -> None:
        """Test get_file_paths raises NotADirectoryError for file path."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            mock_page = MagicMock()
            uploader = DataLumosFileUploader(mock_page)
            with self.assertRaises(NotADirectoryError):
                uploader.get_file_paths(path)
        finally:
            Path(path).unlink(missing_ok=True)
