"""
Bureau of Transportation Statistics (BTS) sourcing module for DRP Pipeline.

Enumerates datasets from the ROSA P BTS Products collection via the JSON export
API (Playwright-backed) and creates ``sourced`` storage records. Run via
orchestrator when ``Args.source`` is ``bts``::

    python main.py sourcing
"""

from __future__ import annotations

from typing import Any

from duplicate_checking import DuplicateChecker
from sourcing.BtsCandidateFetcher import BtsCandidateFetcher, record_id_from_source_url
from sourcing.SourcingBase import SourcingBase
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


class BtsSourcing(SourcingBase):
    """
    Source BTS datasets into Storage from the configured ROSA P collection.

    Uses collection JSON export rather than spreadsheet rows. Already-sourced
    record IDs are skipped before insert.
    """

    def __init__(
        self,
        *,
        fetcher: BtsCandidateFetcher | None = None,
    ) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
        """
        self._fetcher = fetcher or BtsCandidateFetcher()

    def run(self, drpid: int) -> None:
        """
        Enumerate BTS datasets and insert new rows into Storage.

        ``Args.num_rows`` limits how many pending datasets are inserted per run.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)

        limit = Args.num_rows
        Logger.info("BTS sourcing: starting enumeration (limit=%s)", limit)

        try:
            all_rows = self._fetcher.list_dataset_rows()
        finally:
            self._fetcher.close()

        pending_rows = self._pending_rows(all_rows)
        batch_rows = pending_rows[:limit] if limit is not None else pending_rows
        checker = DuplicateChecker()
        inserted = 0
        skipped_dupes = 0
        failed = 0
        assigned_ids: list[int] = []

        Logger.info(
            "BTS sourcing: %s dataset(s) in catalog, %s already sourced, "
            "%s pending; processing %s this run (batch limit=%s)",
            len(all_rows),
            len(all_rows) - len(pending_rows),
            len(pending_rows),
            len(batch_rows),
            limit,
        )

        for index, row in enumerate(batch_rows, 1):
            source_url = row["url"]
            try:
                if self.is_duplicate_in_storage(source_url, checker):
                    skipped_dupes += 1
                    continue

                new_drpid = Storage.create_record(source_url)
                assigned_ids.append(new_drpid)
                Storage.update_record(new_drpid, self._storage_fields_from_row(row))
                inserted += 1
            except Exception as exc:
                failed += 1
                Logger.error("BTS record %s failed: %s", source_url, exc)
                continue

            if index <= 20 or index % 25 == 0 or index == len(batch_rows):
                Logger.info("BTS sourcing progress: %s/%s", index, len(batch_rows))

        remaining = len(pending_rows) - len(batch_rows)
        Logger.info(
            "BTS sourcing complete: %s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s pending for next batch",
            inserted,
            self.format_id_range(assigned_ids),
            failed,
            skipped_dupes,
            remaining,
        )

    def _pending_rows(self, all_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return rows whose record IDs are not yet stored."""
        stored_ids = self._stored_record_ids()
        pending: list[dict[str, str]] = []
        for row in all_rows:
            record_id = row.get("record_id") or record_id_from_source_url(row["url"])
            if record_id and record_id in stored_ids:
                continue
            pending.append(row)
        return pending

    def _stored_record_ids(self) -> set[str]:
        """Parse ROSA P record ids from stored BTS view URLs."""
        stored: set[str] = set()
        for source_url in Storage.list_source_urls():
            record_id = record_id_from_source_url(source_url)
            if record_id is not None:
                stored.add(record_id)
        return stored

    def _storage_fields_from_row(self, row: dict[str, str]) -> dict[str, Any]:
        """Map a candidate row to Storage update fields."""
        return {
            "title": row.get("title", ""),
            "agency": row.get("agency", ""),
            "office": row.get("office", ""),
            "status": "sourced",
        }
