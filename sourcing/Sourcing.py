"""
Sourcing module for DRP Pipeline.

Obtains candidate source URLs from configured sources (e.g. DRP Data_Inventories
spreadsheet), performs duplicate and availability checks, and creates storage
records. Duplicate-in-storage is not created; an Error is logged. Other outcomes
create a row with status: dupe_in_DL, not_found (URL 404 or equivalent), sourcing (good), or Error.
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
        Process configured sources: obtain candidate URLs, create storage records.
        Duplicate URL already in storage: no row created, Error logged. Other
        outcomes create a row with status: dupe_in_DL, not_found (404 or equivalent), sourcing (good), or Error.

        Args:
            drpid: DRPID of project to process. Use -1 for sourcing (no specific project).
        """
        from utils.Args import Args
        from utils.Logger import Logger
        from utils.url_utils import fetch_page_body
        from duplicate_checking import DuplicateChecker

        num_rows = Args.num_rows
        rows, skipped_count = self.get_candidate_urls(limit=num_rows)

        successfully_added = 0
        dupes_in_storage = 0
        dupes_in_datalumos = 0
        not_found_count = 0
        error_count = 0
        assigned_ids: list[int] = []
        checker = DuplicateChecker()

        for row in rows:
            url = row["url"]
            office = row.get("office", "")
            agency = row.get("agency", "")

            if checker.exists_in_storage(url):
                dupes_in_storage += 1
                Logger.error(f"Duplicate source URL already in storage, skipping (no row created): {url}")
                continue

            new_drpid = Storage.create_record(url)
            assigned_ids.append(new_drpid)

            # Check datalumos (turned off for now; structure ready)
            if False:  # checker.exists_in_datalumos(url):
                status = "dupe_in_DL"
                dupes_in_datalumos += 1
                update_fields = {"status": status, "office": office, "agency": agency}
                Storage.update_record(new_drpid, update_fields)
                continue

            # Check URL availability (404 or equivalent)
            try:
                status_code, _body, _content_type, _is_logical_404 = fetch_page_body(url)
                if status_code == 404:
                    status = "not_found"
                    not_found_count += 1
                    update_fields = {"status": status, "office": office, "agency": agency}
                else:
                    status = "sourcing"
                    successfully_added += 1
                    update_fields = {"status": status, "office": office, "agency": agency}
                Storage.update_record(new_drpid, update_fields)
            except Exception as e:
                error_count += 1
                update_fields = {
                    "status": "Error",
                    "office": office,
                    "agency": agency,
                    "errors": str(e),
                }
                Storage.update_record(new_drpid, update_fields)

        id_range_str = ""
        if assigned_ids:
            min_id = min(assigned_ids)
            max_id = max(assigned_ids)
            id_range_str = f" (DRPID: {min_id})" if min_id == max_id else f" (DRPIDs: {min_id}-{max_id})"

        Logger.info(
            f"Sourcing complete: {successfully_added} good (sourcing){id_range_str}, "
            f"{dupes_in_storage} dupe_in_storage (skipped, no row), {dupes_in_datalumos} dupe_in_DL, "
            f"{not_found_count} not_found, {error_count} errors, {skipped_count} skipped by filtering"
        )

    def get_candidate_urls(self, limit: int | None = None) -> tuple[list[dict[str, str]], int]:
        """
        Obtain candidate source URLs and Office/Agency from the configured spreadsheet.

        Delegates to SpreadsheetCandidateFetcher. Limit from orchestrator.

        Returns:
            Tuple of (list of dicts with keys url, office, agency; count of skipped rows)
        """
        fetcher = SpreadsheetCandidateFetcher()
        return fetcher.get_candidate_urls(limit=limit)
