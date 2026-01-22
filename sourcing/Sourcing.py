"""
Sourcing module for DRP Pipeline.

Obtains candidate source URLs from parameterized sources (e.g. DRP Data_Inventories
spreadsheet), performs duplicate prevention and availability checks, and creates
storage records with generated IDs for each new candidate.
"""

from typing import TYPE_CHECKING

from .SourceConfig import SourceConfig

if TYPE_CHECKING:
    from storage.StorageProtocol import StorageProtocol


class Sourcing:
    """
    Orchestrates sourcing of candidate URLs: fetch from configured sources,
    check duplicates and availability, create storage records.
    """

    def __init__(self, storage: "StorageProtocol") -> None:
        """
        Initialize Sourcing with a storage backend.

        Args:
            storage: Storage implementation for creating and querying records.
        """
        self._storage = storage

    def run(self, sources: list[SourceConfig]) -> None:
        """
        Process all configured sources: obtain candidate URLs, then for each
        candidate run duplicate check, availability check, and create storage
        record when appropriate.

        Args:
            sources: List of source configs (e.g. spreadsheet/tab + filter).
        """
        ...

    def get_candidate_urls(self, source: SourceConfig) -> list[str]:
        """
        Obtain candidate source URLs from a parameterized source.

        E.g. read from a spreadsheet tab and apply filter criteria.

        Args:
            source: Configuration specifying spreadsheet, tab, and filter.

        Returns:
            List of candidate URLs to process.
        """
        return []

    def process_candidate(self, url: str) -> bool:
        """
        Process a single candidate URL: duplicate check, availability check,
        then create storage record and generate ID if both pass.

        If the URL is already in the repository, no further processing.
        If the source URL is not available, no further processing.

        Args:
            url: Candidate source URL.

        Returns:
            True if a storage record was created; False if skipped (duplicate
            or unavailable).
        """
        return False

    def is_duplicate(self, url: str) -> bool:
        """
        Check whether the URL already exists in the repository.

        Used for duplicate prevention before creating a new record.

        Args:
            url: Candidate source URL.

        Returns:
            True if URL is already stored; False otherwise.
        """
        return False

    def is_source_available(self, url: str) -> bool:
        """
        Check whether the source URL is reachable/available.

        If not available, we cannot proceed with collection for this URL.

        Args:
            url: Candidate source URL.

        Returns:
            True if URL is available; False otherwise.
        """
        return True

    def create_storage_record_and_id(self, url: str) -> int:
        """
        Create a storage record for the URL and return its generated ID.

        Args:
            url: Source URL for the new record.

        Returns:
            The DRPID of the created record.
        """
        return self._storage.create_record(url)
