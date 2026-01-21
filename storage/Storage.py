"""
Storage protocol interface for DRP Pipeline.

Defines the Storage protocol that all storage implementations must follow.

Example usage:
    from storage.Storage import Storage
    from storage.StorageSQLLite import StorageSQLLite
    
    # Use protocol for type hints
    storage: Storage = StorageSQLLite()
    storage.initialize(db_path="drp_pipeline.db")
"""

from pathlib import Path
from typing import Optional, Protocol, Dict, Any


class Storage(Protocol):
    """
    Protocol defining the storage API interface.
    
    Any class implementing this protocol must provide these methods
    for managing project records.
    """
    
    def initialize(self, db_path: Optional[Path] = None) -> None:
        """
        Initialize the storage backend.
        
        Args:
            db_path: Optional path to storage file/database.
        """
        ...
    
    def create_record(self, source_url: str) -> int:
        """
        Create a new record with the given source_url.
        
        Args:
            source_url: The source URL for the project
            
        Returns:
            The DRPID of the created record
        """
        ...
    
    def update_record(self, drpid: int, values: Dict[str, Any]) -> None:
        """
        Update an existing record with the provided values.
        
        Only the columns specified in values are updated. DRPID and source_url
        cannot be updated.
        
        Args:
            drpid: The DRPID of the record to update
            values: Dictionary of column names and values to update
            
        Raises:
            ValueError: If record doesn't exist or if trying to update DRPID/source_url
        """
        ...
    
    def get(self, drpid: int) -> Optional[Dict[str, Any]]:
        """
        Get a record by DRPID.
        
        Args:
            drpid: The DRPID of the record to retrieve
            
        Returns:
            Dictionary of non-null column values, or None if record not found
        """
        ...
    
    def delete(self, drpid: int) -> None:
        """
        Delete a record by DRPID.
        
        Args:
            drpid: The DRPID of the record to delete
            
        Raises:
            ValueError: If record doesn't exist
        """
        ...
