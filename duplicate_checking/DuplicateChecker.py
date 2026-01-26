"""
Duplicate checker for DRP Pipeline.

Checks whether a proposed source_url already exists in Storage or in
external repositories (e.g. datalumos). Use to avoid adding duplicates.
"""

from typing import TYPE_CHECKING

from duplicate_checking.datalumos_search import verify_source_url_in_datalumos

if TYPE_CHECKING:
    from storage.StorageProtocol import StorageProtocol


class DuplicateChecker:
    """
    Checks for duplicate source URLs in Storage and external repos (e.g. datalumos).
    """

    def __init__(self) -> None:
        """
        Initialize DuplicateChecker. Uses Storage singleton (call Storage.initialize() first).
        """
        # Storage methods are accessed directly on the Storage class, no need to store instance
        pass

    def exists_in_storage(self, source_url: str) -> bool:
        """
        Check whether the proposed source_url already exists in the current
        Storage database.

        Args:
            source_url: The URL to check.

        Returns:
            True if a record with that source_url exists, False otherwise.
        """
        from storage import Storage
        return Storage.exists_by_source_url(source_url)

    def exists_in_datalumos(self, source_url: str) -> bool:
        """
        Check whether the proposed source_url already exists in the datalumos
        repository (https://www.datalumos.org).

        Searches datalumos, navigates to each result page, and returns True only
        if some result's "Original Distribution URL:" <a> text matches the search
        URL. On navigation failure or no match, logs a warning and returns False.

        Args:
            source_url: The URL to check (e.g. a data.cdc.gov about_data link).

        Returns:
            True if a matching Original Distribution URL is found, False otherwise.
        """
        return verify_source_url_in_datalumos(source_url)
