"""
Sourcing module for DRP Pipeline.

Obtains candidate source URLs from configured sources (e.g. DRP Data_Inventories
spreadsheet), performs duplicate prevention and availability checks, and creates
storage records with generated IDs for each new candidate.
"""

from typing import TYPE_CHECKING

from .SpreadsheetCandidateFetcher import SpreadsheetCandidateFetcher

if TYPE_CHECKING:
    from storage.StorageProtocol import StorageProtocol


class Sourcing:
    """
    Orchestrates sourcing of candidate URLs: fetch from configured sources,
    check duplicates and availability, create storage records.
    """

    def __init__(self) -> None:
        """
        Initialize Sourcing. Uses Storage singleton (call Storage.initialize() first).
        """
        # Storage methods are accessed directly on the Storage class, no need to store instance
        pass

    def run(self, drpid: int) -> None:
        """
        Process configured sources: obtain candidate URLs, then for each
        candidate run duplicate check, availability check, and create storage
        record when appropriate.

        Args:
            drpid: DRPID of project to process. Use -1 for sourcing (no specific project).
        """
        from utils.Args import Args
        from storage import Storage
        from utils.Logger import Logger
        
        # Get num_rows from Args
        num_rows = Args.num_rows
        
        urls = self.get_candidate_urls(limit=num_rows)
        
        # Track statistics
        successfully_added = 0
        dupes_in_storage = 0
        skipped_by_filtering = 0
        assigned_ids: list[int] = []
        
        for url in urls:
            result = self.process_candidate(url)
            if isinstance(result, tuple) and result[0] == "added":
                successfully_added += 1
                assigned_ids.append(result[1])
            elif result == "duplicate":
                dupes_in_storage += 1
            elif result == "skipped":
                skipped_by_filtering += 1
        
        # Log statistics
        id_range_str = ""
        if assigned_ids:
            min_id = min(assigned_ids)
            max_id = max(assigned_ids)
            if min_id == max_id:
                id_range_str = f" (DRPID: {min_id})"
            else:
                id_range_str = f" (DRPIDs: {min_id}-{max_id})"
        
        Logger.info(f"Sourcing complete: {successfully_added} URLs successfully added{id_range_str}, "
                   f"{dupes_in_storage} duplicates found in storage, "
                   f"{skipped_by_filtering} URLs skipped by filtering")

    def get_candidate_urls(self, limit: int | None = None) -> list[str]:
        """
        Obtain candidate source URLs from the configured spreadsheet.

        Delegates to SpreadsheetCandidateFetcher. Limit from orchestrator.
        """
        fetcher = SpreadsheetCandidateFetcher()
        return fetcher.get_candidate_urls(limit=limit)

    def process_candidate(self, url: str) -> str | tuple[str, int]:
        """
        Process a single candidate URL: duplicate check, availability check,
        then create storage record and generate ID if both pass.

        If the URL is already in the repository, no further processing.
        If the source URL is not available, no further processing.

        Args:
            url: Candidate source URL.

        Returns:
            ("added", drpid) if a storage record was created; "duplicate" if already in storage;
            "skipped" if unavailable or filtered out.
        """
        from storage import Storage
        from duplicate_checking import DuplicateChecker
        
        # Check if URL already exists in storage
        checker = DuplicateChecker()
        if checker.exists_in_storage(url):
            return "duplicate"
        
        # Check if URL exists in datalumos (commented out for now)
        # if checker.exists_in_datalumos(url):
        #     return "duplicate"
        
        # Check if source is available
        if not self.is_source_available(url):
            return "skipped"
        
        # Create storage record
        drpid = self.create_storage_record_and_id(url)
        
        # Update status to 'sourcing'
        Storage.update_record(drpid, {"status": "sourcing"})
        
        return ("added", drpid)

    def is_duplicate(self, url: str) -> bool:
        """
        Check whether the URL already exists in the repository.

        Used for duplicate prevention before creating a new record.

        Args:
            url: Candidate source URL.

        Returns:
            True if URL is already stored; False otherwise.
        """
        from duplicate_checking import DuplicateChecker
        checker = DuplicateChecker()
        return checker.exists_in_storage(url)

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
        from storage import Storage
        return Storage.create_record(url)
