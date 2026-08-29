"""
Spreadsheet-based sourcing for DRP Pipeline.

Reads candidate URLs from the configured Google Sheet, checks availability,
and creates storage records.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Tuple

from duplicate_checking import DuplicateChecker
from sourcing.SourcingBase import SourcingBase
from sourcing.SpreadsheetCandidateFetcher import SpreadsheetCandidateFetcher
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


def _check_one(
    item: Tuple[int, str, str, str], timeout: int
) -> Tuple[int, str, str, str, int, str, Any, bool, Any]:
    """
    Fetch one URL and return availability metadata for post-processing.

    Args:
        item: Tuple of (new_drpid, url, office, agency).
        timeout: HTTP timeout in seconds.

    Returns:
        Tuple ending with exception (or None) from fetch_page_body.
    """
    from utils.url_utils import fetch_page_body

    new_drpid, url, office, agency = item
    try:
        status_code, body, content_type, is_logical_404 = fetch_page_body(
            url, timeout=timeout
        )
        return (
            new_drpid,
            url,
            office,
            agency,
            status_code,
            body,
            content_type,
            is_logical_404,
            None,
        )
    except Exception as exc:
        return (new_drpid, url, office, agency, -1, "", None, False, exc)


class SpreadsheetSourcing(SourcingBase):
    """
    Source projects from the DRP inventory Google Sheet.

    Performs duplicate and HTTP availability checks before marking rows sourced.
    """

    def run(self, drpid: int) -> None:
        """
        Process spreadsheet rows and create storage records.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)

        num_rows = Args.num_rows
        rows, skipped_count = self.get_candidate_urls(limit=num_rows)
        timeout = int(getattr(Args, "sourcing_fetch_timeout", 15) or 15)
        workers = max(1, int(Args.max_workers or 1))

        successfully_added = 0
        dupes_in_storage = 0
        dupes_in_datalumos = 0
        not_found_count = 0
        error_count = 0
        assigned_ids: List[int] = []
        checker = DuplicateChecker()
        to_fetch: List[Tuple[int, str, str, str]] = []

        for row in rows:
            url = row["url"]
            office = row.get("office", "")
            agency = row.get("agency", "")

            if self.is_duplicate_in_storage(url, checker):
                dupes_in_storage += 1
                continue

            new_drpid = Storage.create_record(url)
            assigned_ids.append(new_drpid)

            if False:  # checker.exists_in_datalumos(url):
                dupes_in_datalumos += 1
                Storage.update_record(
                    new_drpid,
                    {"status": "dupe_in_DL", "office": office, "agency": agency},
                )
                continue

            to_fetch.append((new_drpid, url, office, agency))

        total = len(to_fetch)
        if total > 0:
            Logger.info(
                "Sourcing: checking availability for %s URLs "
                "(max_workers=%s, timeout=%ss)",
                total,
                workers,
                timeout,
            )

        results = self._check_urls(to_fetch, timeout, workers, total)

        for result in results:
            new_drpid, _url, office, agency, status_code, _body, _ct, _logical_404, exc = (
                result
            )
            if exc is not None:
                error_count += 1
                Storage.update_record(
                    new_drpid,
                    {
                        "status": "error",
                        "office": office,
                        "agency": agency,
                        "errors": str(exc),
                    },
                )
            elif status_code == 404:
                not_found_count += 1
                Storage.update_record(
                    new_drpid,
                    {"status": "not_found", "office": office, "agency": agency},
                )
            else:
                successfully_added += 1
                Storage.update_record(
                    new_drpid,
                    {"status": "sourced", "office": office, "agency": agency},
                )

        Logger.info(
            "Sourcing complete: %s good (sourcing)%s, "
            "%s dupe_in_storage (skipped, no row), %s dupe_in_DL, "
            "%s not_found, %s errors, %s skipped by filtering",
            successfully_added,
            self.format_id_range(assigned_ids),
            dupes_in_storage,
            dupes_in_datalumos,
            not_found_count,
            error_count,
            skipped_count,
        )

    def get_candidate_urls(
        self, limit: int | None = None
    ) -> tuple[list[dict[str, str]], int]:
        """
        Obtain candidate source URLs from the configured spreadsheet.

        Args:
            limit: Max rows to return; None means unlimited.

        Returns:
            Tuple of candidate row dicts and skipped row count.
        """
        fetcher = SpreadsheetCandidateFetcher()
        return fetcher.get_candidate_urls(limit=limit)

    def _check_urls(
        self,
        to_fetch: List[Tuple[int, str, str, str]],
        timeout: int,
        workers: int,
        total: int,
    ) -> List[Tuple[int, str, str, str, int, str, Any, bool, Any]]:
        """
        Check URL availability sequentially or in parallel.

        Args:
            to_fetch: Pending rows awaiting HTTP checks.
            timeout: Per-request timeout in seconds.
            workers: Max concurrent workers.
            total: Count of URLs (for progress logging).

        Returns:
            List of check results in completion order when parallel.
        """
        results: List[Tuple[int, str, str, str, int, str, Any, bool, Any]] = []
        if workers <= 1:
            for index, item in enumerate(to_fetch, 1):
                results.append(_check_one(item, timeout))
                if total <= 20 or index % 10 == 0 or index == total:
                    Logger.info("Sourcing progress: %s/%s URLs checked", index, total)
            return results

        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_check_one, item, timeout) for item in to_fetch]
            for future in as_completed(futures):
                results.append(future.result())
                completed += 1
                if total <= 20 or completed % 10 == 0 or completed == total:
                    Logger.info(
                        "Sourcing progress: %s/%s URLs checked", completed, total
                    )
        return results
