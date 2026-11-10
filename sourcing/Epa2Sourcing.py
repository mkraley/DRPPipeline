"""
EPA2 sourcing module for DRP Pipeline.

Enumerates the EDG Clip and Ship hub catalog and creates ``sourced`` storage
records. Run via orchestrator when ``Args.source`` is ``epa2``::

    python main.py source --source epa2
"""

from __future__ import annotations

from typing import Any

from duplicate_checking import DuplicateChecker
from sourcing.EpaHubCandidateFetcher import (
    EpaHubCandidateFetcher,
    item_id_from_source_url,
)
from sourcing.SourcingBase import SourcingBase
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

_LABEL = "EPA2"


class Epa2Sourcing(SourcingBase):
    """
    Source EDG Clip and Ship items into Storage.

    Already-sourced ArcGIS item ids are skipped before insert.
    """

    def __init__(self, *, fetcher: EpaHubCandidateFetcher | None = None) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
        """
        self._fetcher = fetcher or EpaHubCandidateFetcher()

    def run(self, drpid: int) -> None:
        """
        Enumerate Clip and Ship items and insert new rows into Storage.

        ``Args.num_rows`` limits how many pending items are inserted per run.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)
        limit = Args.num_rows
        Logger.info("%s sourcing: starting catalog enumeration (limit=%s)", _LABEL, limit)
        try:
            all_rows = self._fetcher.list_dataset_rows()
        finally:
            self._fetcher.close()
        self._insert_pending(all_rows, limit)

    def _insert_pending(self, all_rows: list[dict[str, str]], limit: int | None) -> None:
        """Insert pending catalog rows up to the batch limit."""
        pending_rows = self._pending_rows(all_rows)
        batch_rows = pending_rows[:limit] if limit is not None else pending_rows
        checker = DuplicateChecker()
        inserted = 0
        skipped_dupes = 0
        failed = 0
        assigned_ids: list[int] = []
        self._log_batch(all_rows, pending_rows, batch_rows, limit)
        for index, row in enumerate(batch_rows, 1):
            outcome = self._insert_one(row, checker, assigned_ids)
            if outcome == "inserted":
                inserted += 1
            elif outcome == "duplicate":
                skipped_dupes += 1
            else:
                failed += 1
            if index <= 20 or index % 25 == 0 or index == len(batch_rows):
                Logger.info("%s sourcing progress: %s/%s", _LABEL, index, len(batch_rows))
        remaining = len(pending_rows) - len(batch_rows)
        Logger.info(
            "%s sourcing complete: %s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s pending for next batch",
            _LABEL,
            inserted,
            self.format_id_range(assigned_ids),
            failed,
            skipped_dupes,
            remaining,
        )

    def _insert_one(
        self,
        row: dict[str, str],
        checker: DuplicateChecker,
        assigned_ids: list[int],
    ) -> str:
        """
        Insert one candidate row.

        Args:
            row: Candidate from the hub fetcher.
            checker: Duplicate checker bound to current Storage.
            assigned_ids: DRPIDs created during this run, updated in place.

        Returns:
            ``inserted``, ``duplicate``, or ``failed``.
        """
        source_url = row["url"]
        try:
            if self.is_duplicate_in_storage(source_url, checker):
                return "duplicate"
            new_drpid = Storage.create_record(source_url)
            assigned_ids.append(new_drpid)
            Storage.update_record(new_drpid, self._storage_fields_from_row(row))
        except Exception as exc:
            Logger.error("%s record %s failed: %s", _LABEL, source_url, exc)
            return "failed"
        return "inserted"

    def _pending_rows(self, all_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return rows whose ArcGIS item ids are not yet stored."""
        stored_ids = self._stored_item_ids()
        pending: list[dict[str, str]] = []
        for row in all_rows:
            item_id = row.get("record_id") or item_id_from_source_url(row["url"])
            if item_id and item_id in stored_ids:
                continue
            pending.append(row)
        return pending

    def _stored_item_ids(self) -> set[str]:
        """Return ArcGIS item ids already in Storage."""
        stored: set[str] = set()
        for source_url in Storage.list_source_urls():
            item_id = item_id_from_source_url(source_url)
            if item_id is not None:
                stored.add(item_id)
        return stored

    def _storage_fields_from_row(self, row: dict[str, str]) -> dict[str, Any]:
        """Map a candidate row to Storage update fields."""
        fields: dict[str, Any] = {
            "title": row.get("title", ""),
            "summary": row.get("summary", ""),
            "agency": row.get("agency", ""),
            "office": row.get("office", ""),
            "status": "sourced",
        }
        item_type = row.get("item_type", "").strip()
        if item_type:
            fields["collection_notes"] = f"EDG Clip and Ship: {item_type}"
        return fields

    def _log_batch(
        self,
        all_rows: list[dict[str, str]],
        pending_rows: list[dict[str, str]],
        batch_rows: list[dict[str, str]],
        limit: int | None,
    ) -> None:
        """Log how many catalog rows this run will process."""
        Logger.info(
            "%s sourcing: %s item(s) in catalog, %s already sourced, "
            "%s pending; processing %s this run (batch limit=%s)",
            _LABEL,
            len(all_rows),
            len(all_rows) - len(pending_rows),
            len(pending_rows),
            len(batch_rows),
            limit,
        )
