"""
Unit tests for Storage factory.
"""

import tempfile
import unittest
from pathlib import Path

from utils.Args import Args
from utils.Logger import Logger
from storage import Storage


class TestStorage(unittest.TestCase):
    """Test cases for Storage factory."""
    
    def setUp(self) -> None:
        """Set up test environment before each test."""
        import sys
        # Save and restore original argv to prevent test interference
        self._original_argv = sys.argv.copy()
        # Set minimal argv to avoid Typer command parsing issues
        sys.argv = ["test"]
        
        # Initialize Args and Logger (required by Storage)
        Args.initialize()
        Logger.initialize(log_level="WARNING")  # Reduce log noise during tests
        
        # Create temporary database file
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        import sys
        # Restore original argv
        sys.argv = self._original_argv
        # Clean up temp directory
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def test_initialize_storage_sqlite(self) -> None:
        """Test initializing StorageSQLLite via factory."""
        storage = Storage.initialize('StorageSQLLite', db_path=self.test_db_path)
        
        # Verify it's initialized and can be used
        self.assertTrue(hasattr(storage, '_initialized'))
        self.assertTrue(storage._initialized)
        
        # Verify it can create records
        drpid = storage.create_record("https://example.com")
        self.assertEqual(drpid, 1)
        
        storage.close()
    
    def test_initialize_invalid_implementation(self) -> None:
        """Test that invalid implementation name raises ValueError."""
        with self.assertRaises(ValueError) as cm:
            Storage.initialize('InvalidStorage')
        
        self.assertIn("Unknown storage implementation", str(cm.exception))
        self.assertIn("InvalidStorage", str(cm.exception))
    
    def test_initialize_with_default_path(self) -> None:
        """Test initializing with default path."""
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            storage = Storage.initialize('StorageSQLLite')
            
            # Verify default path was used
            default_path = Path.cwd() / "drp_pipeline.db"
            self.assertEqual(storage.get_db_path(), default_path)
            self.assertTrue(default_path.exists())
            
            storage.close()
        finally:
            os.chdir(original_cwd)
