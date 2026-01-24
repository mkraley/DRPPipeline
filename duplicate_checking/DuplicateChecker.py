"""
Duplicate checker for DRP Pipeline.

Checks whether a proposed source_url already exists in Storage or in
external repositories (e.g. datalumos). Use to avoid adding duplicates.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storage.StorageProtocol import StorageProtocol


class DuplicateChecker:
    """
    Checks for duplicate source URLs in Storage and (future) external repos.
    """

    def __init__(self, storage: "StorageProtocol") -> None:
        """
        Create a duplicate checker that uses the given Storage implementation.

        Args:
            storage: Initialized Storage instance to check against.
        """
        self._storage = storage

    def exists_in_storage(self, source_url: str) -> bool:
        """
        Check whether the proposed source_url already exists in the current
        Storage database.

        Args:
            source_url: The URL to check.

        Returns:
            True if a record with that source_url exists, False otherwise.
        """
        return self._storage.exists_by_source_url(source_url)
