"""
Storage factory for DRP Pipeline.

Provides a factory method to create and initialize storage implementations
without requiring direct imports of implementation classes.

Example usage:
    from storage import Storage
    
    # Initialize storage using implementation class name
    storage = Storage.initialize('StorageSQLLite', db_path="drp_pipeline.db")
    
    # Create a record
    drpid = storage.create_record("https://example.com")
    
    # Get a record
    record = storage.get(drpid)
    
    # Update a record
    storage.update_record(drpid, {"title": "My Project", "status": "active"})
    
    # Delete a record
    storage.delete(drpid)
"""

from pathlib import Path
from typing import Optional

from storage.StorageProtocol import StorageProtocol


class Storage:
    """Factory class for creating and initializing storage implementations."""
    
    # Registry mapping class names to their module paths
    _implementations = {
        'StorageSQLLite': 'storage.StorageSQLLite.StorageSQLLite',
    }
    
    @classmethod
    def initialize(cls, implementation: str, db_path: Optional[Path] = None) -> StorageProtocol:
        """
        Create and initialize a storage implementation.
        
        Args:
            implementation: Name of the implementation class (e.g., 'StorageSQLLite')
            db_path: Optional path to storage file/database
            
        Returns:
            Initialized storage instance conforming to StorageProtocol
            
        Raises:
            ValueError: If implementation name is not recognized
            ImportError: If the implementation class cannot be imported
            RuntimeError: If initialization fails
        """
        if implementation not in cls._implementations:
            raise ValueError(
                f"Unknown storage implementation: {implementation}. "
                f"Available implementations: {', '.join(cls._implementations.keys())}"
            )
        
        # Dynamically import the implementation class
        module_path = cls._implementations[implementation]
        module_name, class_name = module_path.rsplit('.', 1)
        
        try:
            module = __import__(module_name, fromlist=[class_name])
            implementation_class = getattr(module, class_name)
        except (ImportError, AttributeError) as e:
            raise ImportError(
                f"Failed to import storage implementation '{implementation}': {e}"
            ) from e
        
        # Create instance and initialize it
        instance = implementation_class()
        instance.initialize(db_path=db_path)
        
        return instance
