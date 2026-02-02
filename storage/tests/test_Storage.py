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
        sys.argv = ["test", "noop"]

        # Initialize Args and Logger (required by Storage)
        Args.initialize()
        Logger.initialize(log_level="WARNING")  # Reduce log noise during tests
        
        # Create temporary database file
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        import sys
        # Reset singleton for next test
        Storage.reset()
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
    
    def test_direct_method_access(self) -> None:
        """Test that Storage methods can be called directly on the class."""
        Storage.initialize('StorageSQLLite', db_path=self.test_db_path)
        
        # Should be able to call methods directly
        drpid = Storage.create_record("https://example.com")
        self.assertIsInstance(drpid, int)
        
        record = Storage.get(drpid)
        self.assertIsNotNone(record)
        self.assertEqual(record["source_url"], "https://example.com")
        
        Storage.close()
    
    def test_method_access_before_initialize_raises(self) -> None:
        """Test that method access before initialize() raises RuntimeError."""
        Storage.reset()  # Ensure no instance exists
        with self.assertRaises(RuntimeError) as cm:
            Storage.create_record("https://example.com")
        self.assertIn("not been initialized", str(cm.exception))
    
    def test_initialize_twice_returns_same_instance(self) -> None:
        """Test calling initialize() twice returns the same singleton instance."""
        storage1 = Storage.initialize('StorageSQLLite', db_path=self.test_db_path)
        storage2 = Storage.initialize('StorageSQLLite', db_path=self.test_db_path)
        
        self.assertIs(storage1, storage2)
        storage1.close()
    
    def test_reset_clears_singleton(self) -> None:
        """Test reset() clears the singleton so a new instance can be created."""
        storage1 = Storage.initialize('StorageSQLLite', db_path=self.test_db_path)
        storage1.close()
        Storage.reset()
        
        # Should be able to initialize again
        storage2 = Storage.initialize('StorageSQLLite', db_path=self.test_db_path)
        self.assertIsNot(storage1, storage2)
        storage2.close()
