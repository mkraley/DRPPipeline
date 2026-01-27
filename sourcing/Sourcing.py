"""
Sourcing module for DRP Pipeline.

Obtains candidate source URLs from configured sources (e.g. DRP Data_Inventories
spreadsheet), performs duplicate prevention and availability checks, and creates
storage records with generated IDs for each new candidate.
"""

from typing import TYPE_CHECKING

from storage import Storage
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
        Initialize Sourcing. 
        """
        # Storage methods are accessed directly on the Storage class, no need to store instance
        pass

    def run(self, drpid: int) -> None:
        """
        Process configured sources: obtain candidate URLs, create storage records,
        then check for duplicates and mark them appropriately.

        Args:
            drpid: DRPID of project to process. Use -1 for sourcing (no specific project).
        """
        from utils.Args import Args
        from utils.Logger import Logger
        from duplicate_checking import DuplicateChecker
        import sqlite3
        
        # Get num_rows from Args
        num_rows = Args.num_rows
        
        # Get candidate URLs and skipped count from fetcher
        urls, skipped_count = self.get_candidate_urls(limit=num_rows)
        
        # Track statistics
        successfully_added = 0
        dupes_in_storage = 0
        dupes_in_datalumos = 0
        assigned_ids: list[int] = []
        checker = DuplicateChecker()
        
        # Check for duplicates before creating records
        for url in urls:
            duplicate_reason = None
            
            # Check if URL already exists in storage
            if checker.exists_in_storage(url):
                dupes_in_storage += 1
                continue  # Skip to next URL, don't create record
            
            # Check datalumos (commented out for now, but structure ready)
            # if checker.exists_in_datalumos(url):
            #     duplicate_reason = "Duplicate source URL already exists in DataLumos"
            #     dupes_in_datalumos += 1
            
            # Create storage record only if URL is not already in storage
            drpid = Storage.create_record(url)
            assigned_ids.append(drpid)
            
            if duplicate_reason:
                # Mark as error with duplicate reason
                Storage.update_record(drpid, {
                    "status": "Error",
                    "errors": duplicate_reason
                })
            else:
                # Successfully added
                Storage.update_record(drpid, {"status": "sourcing"})
                successfully_added += 1
        
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
                   f"{dupes_in_datalumos} duplicates found in DataLumos, "
                   f"{skipped_count} URLs skipped by filtering")

    def get_candidate_urls(self, limit: int | None = None) -> tuple[list[str], int]:
        """
        Obtain candidate source URLs from the configured spreadsheet.

        Delegates to SpreadsheetCandidateFetcher. Limit from orchestrator.

        Returns:
            Tuple of (list of candidate URLs, count of skipped rows)
        """
        fetcher = SpreadsheetCandidateFetcher()
        return fetcher.get_candidate_urls(limit=limit)
