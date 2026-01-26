"""
Storage protocol interface for DRP Pipeline.

Defines the Storage protocol that all storage implementations must follow.
"""

from pathlib import Path
from typing import Literal, Optional, Protocol, Dict, Any


class StorageProtocol(Protocol):
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
    
    def exists_by_source_url(self, source_url: str) -> bool:
        """
        Check whether a record with the given source_url already exists.
        
        Args:
            source_url: The source URL to look up
            
        Returns:
            True if a record exists, False otherwise
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

    def list_eligible_projects(
        self, prereq_status: Optional[str], limit: Optional[int]
    ) -> list[Dict[str, Any]]:
        """
        List projects eligible for the next module: status == prereq_status and no errors.

        Order by DRPID ASC. Optionally limit the number of rows. Return full row dicts.
        Only the orchestrator should call this; when prereq_status is None, return [].

        Args:
            prereq_status: Required status (e.g. "sourcing" for collectors). None -> [].
            limit: Max rows to return. None = no limit.

        Returns:
            List of full row dicts (all columns, including None for nulls).
        """
        ...

    def append_to_field(
        self, drpid: int, field: Literal["warnings", "errors"], text: str
    ) -> None:
        """
        Append text to the warnings or errors field. Format: one entry per line (newline).

        Args:
            drpid: The DRPID of the record to update.
            field: Either "warnings" or "errors".
            text: Text to append.

        Raises:
            ValueError: If field is not "warnings" or "errors", or record does not exist.
        """
        ...
