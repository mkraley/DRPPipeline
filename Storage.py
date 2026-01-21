"""
Storage module for DRP Pipeline with SQLite database.

Provides database schema, initialization, and query interface for managing
project data. Supports concurrent access using WAL mode.

Example usage:
    from Storage import Storage
    
    # Initialize storage
    Storage.initialize(db_path="drp_pipeline.db")
    
    # Execute queries
    cursor = Storage.execute("SELECT * FROM projects WHERE DRPID = ?", (1,))
    results = cursor.fetchall()
"""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple, Any

from Logger import Logger


class Storage:
    """Storage class providing database access with concurrent support."""
    
    _connection: Optional[sqlite3.Connection] = None
    _db_path: Optional[Path] = None
    _initialized: bool = False
    
    # Table schema definition
    _schema_sql = """
    CREATE TABLE IF NOT EXISTS projects (
        DRPID INTEGER PRIMARY KEY AUTOINCREMENT,
        source_url TEXT NOT NULL UNIQUE,
        folder_path TEXT,
        title TEXT,
        agency TEXT,
        office TEXT,
        summary TEXT,
        keywords TEXT,
        time_start TEXT,
        time_end TEXT,
        data_types TEXT,
        download_date TEXT,
        collection_notes TEXT,
        file_size TEXT,
        datalumos_id TEXT UNIQUE,
        published_url TEXT,
        status TEXT,
        status_notes TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_source_url ON projects(source_url);
    CREATE INDEX IF NOT EXISTS idx_datalumos_id ON projects(datalumos_id);
    CREATE INDEX IF NOT EXISTS idx_status ON projects(status);
    """
    
    @classmethod
    def initialize(cls, db_path: Optional[Path] = None) -> None:
        """
        Initialize the database connection and create schema if needed.
        
        Sets up SQLite with WAL mode for concurrent access. Creates the database
        file and tables if they don't exist.
        
        Args:
            db_path: Path to SQLite database file. If None, uses 'drp_pipeline.db'
                    in the current working directory.
        
        Raises:
            RuntimeError: If initialization fails
        """
        if cls._initialized:
            return
        
        if db_path is None:
            db_path = Path.cwd() / "drp_pipeline.db"
        elif not isinstance(db_path, Path):
            db_path = Path(db_path)
        
        cls._db_path = db_path
        
        try:
            # Create parent directory if it doesn't exist
            cls._db_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Connect to database
            cls._connection = sqlite3.connect(
                str(cls._db_path),
                check_same_thread=False,  # Allow use from multiple threads
                timeout=30.0  # Wait up to 30 seconds for locks
            )
            
            # Enable WAL mode for concurrent reads/writes
            cls._connection.execute("PRAGMA journal_mode=WAL")
            
            # Set other pragmas for better concurrency
            cls._connection.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
            cls._connection.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and speed
            
            # Create schema
            cls._connection.executescript(cls._schema_sql)
            cls._connection.commit()
            
            cls._initialized = True
            Logger.info(f"Storage initialized: {cls._db_path}")
            
        except sqlite3.Error as e:
            cls._connection = None
            cls._initialized = False
            error_msg = f"Failed to initialize database at {cls._db_path}: {e}"
            Logger.error(error_msg)
            raise RuntimeError(error_msg) from e
    
    @classmethod
    def execute(cls, query: str, parameters: Optional[Tuple[Any, ...]] = None) -> sqlite3.Cursor:
        """
        Execute a SQL query and return a cursor.
        
        This method provides a query interface for executing arbitrary SQL.
        For SELECT queries, use the returned cursor to fetch results.
        For INSERT/UPDATE/DELETE, the changes are committed automatically.
        
        Args:
            query: SQL query string (can include ? placeholders for parameters)
            parameters: Optional tuple of parameters for parameterized queries
        
        Returns:
            sqlite3.Cursor object for fetching results
        
        Raises:
            RuntimeError: If Storage is not initialized
            sqlite3.Error: If query execution fails
        
        Example:
            # SELECT query
            cursor = Storage.execute("SELECT * FROM projects WHERE DRPID = ?", (1,))
            rows = cursor.fetchall()
            
            # INSERT query (DRPID is auto-increment, so omit it)
            Storage.execute(
                "INSERT INTO projects (source_url, folder_path) VALUES (?, ?)",
                ("https://example.com", "C:\\data\\project1")
            )
        """
        if not cls._initialized:
            raise RuntimeError("Storage has not been initialized. Call Storage.initialize() first.")
        
        if cls._connection is None:
            raise RuntimeError("Database connection is not available.")
        
        try:
            if parameters:
                cursor = cls._connection.execute(query, parameters)
            else:
                cursor = cls._connection.execute(query)
            
            # Auto-commit for non-SELECT queries
            if not query.strip().upper().startswith("SELECT"):
                cls._connection.commit()
            
            return cursor
            
        except sqlite3.Error as e:
            Logger.error(f"Database query failed: {query[:100]}... Error: {e}")
            raise
    
    @classmethod
    def close(cls) -> None:
        """
        Close the database connection.
        
        Note: The connection will be automatically closed when the process exits,
        but this can be useful for explicit cleanup.
        """
        if cls._connection:
            try:
                cls._connection.close()
                Logger.info("Database connection closed")
            except sqlite3.Error as e:
                Logger.warning(f"Error closing database connection: {e}")
            finally:
                cls._connection = None
                cls._initialized = False
    
    @classmethod
    def get_db_path(cls) -> Path:
        """
        Get the path to the database file.
        
        Returns:
            Path to the database file
        
        Raises:
            RuntimeError: If Storage is not initialized
        """
        if not cls._initialized:
            raise RuntimeError("Storage has not been initialized. Call Storage.initialize() first.")
        
        if cls._db_path is None:
            raise RuntimeError("Database path is not set.")
        
        return cls._db_path
