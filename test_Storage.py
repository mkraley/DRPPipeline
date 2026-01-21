"""
Unit tests for Storage module.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from Args import Args
from Logger import Logger
from Storage import Storage


class TestStorage(unittest.TestCase):
    """Test cases for Storage class."""
    
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
        
        # Reset Storage state
        Storage.close()
        Storage._initialized = False
        Storage._connection = None
        Storage._db_path = None
        
        # Create temporary database file
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db_path = self.temp_dir / "test_drp_pipeline.db"
    
    def tearDown(self) -> None:
        """Clean up after each test."""
        import sys
        Storage.close()
        # Restore original argv
        sys.argv = self._original_argv
        # Clean up temp directory
        if self.temp_dir.exists():
            import shutil
            shutil.rmtree(self.temp_dir)
    
    def test_initialize_default_path(self) -> None:
        """Test Storage initialization with default path."""
        # Change to temp directory for default path test
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(self.temp_dir)
            Storage.initialize()
            self.assertTrue(Storage._initialized)
            self.assertIsNotNone(Storage._connection)
            default_path = Path.cwd() / "drp_pipeline.db"
            self.assertEqual(Storage.get_db_path(), default_path)
            self.assertTrue(default_path.exists())
        finally:
            os.chdir(original_cwd)
    
    def test_initialize_custom_path(self) -> None:
        """Test Storage initialization with custom path."""
        Storage.initialize(db_path=self.test_db_path)
        self.assertTrue(Storage._initialized)
        self.assertIsNotNone(Storage._connection)
        self.assertEqual(Storage.get_db_path(), self.test_db_path)
        self.assertTrue(self.test_db_path.exists())
    
    def test_initialize_creates_schema(self) -> None:
        """Test that initialization creates the projects table."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Check that table exists
        cursor = Storage.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
        )
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "projects")
        
        # Check that indexes exist
        cursor = Storage.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = [row[0] for row in cursor.fetchall()]
        self.assertIn("idx_source_url", indexes)
        self.assertIn("idx_datalumos_id", indexes)
        self.assertIn("idx_status", indexes)
    
    def test_initialize_enables_wal_mode(self) -> None:
        """Test that WAL mode is enabled for concurrent access."""
        Storage.initialize(db_path=self.test_db_path)
        
        cursor = Storage.execute("PRAGMA journal_mode")
        result = cursor.fetchone()
        self.assertEqual(result[0].upper(), "WAL")
    
    def test_initialize_idempotent(self) -> None:
        """Test that initialize can be called multiple times safely."""
        Storage.initialize(db_path=self.test_db_path)
        first_connection = Storage._connection
        
        Storage.initialize(db_path=self.test_db_path)
        self.assertEqual(Storage._connection, first_connection)
    
    def test_execute_select_query(self) -> None:
        """Test executing a SELECT query."""
        Storage.initialize(db_path=self.test_db_path)
        
        cursor = Storage.execute("SELECT 1 as test_value")
        result = cursor.fetchone()
        self.assertEqual(result[0], 1)
    
    def test_execute_insert_query(self) -> None:
        """Test executing an INSERT query with auto-increment DRPID."""
        Storage.initialize(db_path=self.test_db_path)
        
        Storage.execute(
            "INSERT INTO projects (source_url, folder_path) VALUES (?, ?)",
            ("https://example.com", "C:\\data\\project1")
        )
        
        # Verify insert - DRPID should be auto-generated (typically 1)
        cursor = Storage.execute("SELECT * FROM projects WHERE source_url = ?", ("https://example.com",))
        result = cursor.fetchone()
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 1)  # First auto-increment value
        self.assertEqual(result[1], "https://example.com")
        self.assertEqual(result[2], "C:\\data\\project1")
    
    def test_execute_update_query(self) -> None:
        """Test executing an UPDATE query."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Insert test data (DRPID auto-increments)
        Storage.execute(
            "INSERT INTO projects (source_url, folder_path, title) VALUES (?, ?, ?)",
            ("https://example.com", "C:\\data\\project1", "Original Title")
        )
        
        # Update
        Storage.execute(
            "UPDATE projects SET title = ? WHERE DRPID = ?",
            ("Updated Title", 1)
        )
        
        # Verify update
        cursor = Storage.execute("SELECT title FROM projects WHERE DRPID = ?", (1,))
        result = cursor.fetchone()
        self.assertEqual(result[0], "Updated Title")
    
    def test_execute_parameterized_query(self) -> None:
        """Test executing parameterized queries."""
        Storage.initialize(db_path=self.test_db_path)
        
        Storage.execute(
            "INSERT INTO projects (source_url, folder_path) VALUES (?, ?)",
            ("https://example.com", "C:\\data\\project1")
        )
        
        cursor = Storage.execute("SELECT source_url FROM projects WHERE DRPID = ?", (1,))
        result = cursor.fetchone()
        self.assertEqual(result[0], "https://example.com")
    
    def test_get_db_path(self) -> None:
        """Test getting database path."""
        Storage.initialize(db_path=self.test_db_path)
        self.assertEqual(Storage.get_db_path(), self.test_db_path)
    
    def test_get_db_path_not_initialized(self) -> None:
        """Test that get_db_path raises error when not initialized."""
        with self.assertRaises(RuntimeError):
            Storage.get_db_path()
    
    def test_execute_not_initialized(self) -> None:
        """Test that execute raises error when not initialized."""
        with self.assertRaises(RuntimeError):
            Storage.execute("SELECT 1")
    
    def test_close_connection(self) -> None:
        """Test closing the database connection."""
        Storage.initialize(db_path=self.test_db_path)
        self.assertTrue(Storage._initialized)
        
        Storage.close()
        self.assertFalse(Storage._initialized)
        self.assertIsNone(Storage._connection)
    
    def test_schema_all_fields(self) -> None:
        """Test that schema includes all required fields."""
        Storage.initialize(db_path=self.test_db_path)
        
        cursor = Storage.execute("PRAGMA table_info(projects)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        # Check all required fields exist
        required_fields = [
            "DRPID", "source_url", "folder_path", "title", "agency", "office",
            "summary", "keywords", "time_start", "time_end", "data_types",
            "download_date", "collection_notes", "file_size", "datalumos_id",
            "published_url", "status", "status_notes"
        ]
        
        for field in required_fields:
            self.assertIn(field, columns, f"Field {field} missing from schema")
        
        # Verify file_size is TEXT, not INTEGER
        self.assertEqual(columns["file_size"], "TEXT")
        
        # Verify DRPID is INTEGER
        self.assertEqual(columns["DRPID"], "INTEGER")
    
    def test_concurrent_access_simulation(self) -> None:
        """Test that database can handle multiple operations (simulating concurrency)."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Simulate multiple concurrent-like operations
        for i in range(10):
            Storage.execute(
                "INSERT INTO projects (source_url, folder_path) VALUES (?, ?)",
                (f"https://example{i}.com", f"C:\\data\\project{i}")
            )
        
        cursor = Storage.execute("SELECT COUNT(*) FROM projects")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 10)
    
    def test_drpid_auto_increment(self) -> None:
        """Test that DRPID auto-increments."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Insert multiple records
        Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example1.com",))
        Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example2.com",))
        Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example3.com",))
        
        # Verify DRPID values
        cursor = Storage.execute("SELECT DRPID FROM projects ORDER BY DRPID")
        drpids = [row[0] for row in cursor.fetchall()]
        self.assertEqual(drpids, [1, 2, 3])
    
    def test_source_url_unique_constraint(self) -> None:
        """Test that source_url must be unique."""
        Storage.initialize(db_path=self.test_db_path)
        
        Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example.com",))
        
        # Try to insert duplicate source_url - should fail
        with self.assertRaises(sqlite3.IntegrityError):
            Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example.com",))
    
    def test_datalumos_id_unique_constraint(self) -> None:
        """Test that datalumos_id must be unique when provided."""
        Storage.initialize(db_path=self.test_db_path)
        
        Storage.execute(
            "INSERT INTO projects (source_url, datalumos_id) VALUES (?, ?)",
            ("https://example1.com", "DL123")
        )
        
        # Try to insert duplicate datalumos_id - should fail
        with self.assertRaises(sqlite3.IntegrityError):
            Storage.execute(
                "INSERT INTO projects (source_url, datalumos_id) VALUES (?, ?)",
                ("https://example2.com", "DL123")
            )
    
    def test_datalumos_id_nullable(self) -> None:
        """Test that datalumos_id can be null."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Insert without datalumos_id
        Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example.com",))
        
        # Insert with datalumos_id
        Storage.execute(
            "INSERT INTO projects (source_url, datalumos_id) VALUES (?, ?)",
            ("https://example2.com", "DL123")
        )
        
        # Both should succeed
        cursor = Storage.execute("SELECT COUNT(*) FROM projects")
        count = cursor.fetchone()[0]
        self.assertEqual(count, 2)
    
    def test_folder_path_nullable(self) -> None:
        """Test that folder_path can be null."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Insert without folder_path
        Storage.execute("INSERT INTO projects (source_url) VALUES (?)", ("https://example.com",))
        
        # Verify it was inserted with null folder_path
        cursor = Storage.execute("SELECT folder_path FROM projects WHERE source_url = ?", ("https://example.com",))
        result = cursor.fetchone()
        self.assertIsNone(result[0])
    
    def test_source_url_not_null(self) -> None:
        """Test that source_url cannot be null."""
        Storage.initialize(db_path=self.test_db_path)
        
        # Try to insert without source_url - should fail
        with self.assertRaises(sqlite3.IntegrityError):
            Storage.execute("INSERT INTO projects (folder_path) VALUES (?)", ("C:\\data\\project1",))
