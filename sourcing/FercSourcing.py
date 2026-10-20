"""
FERC sourcing module for DRP Pipeline.

Enumerates datasets from the FERC data-assets API and creates ``sourced``
storage records. Run via orchestrator when ``Args.source`` is ``ferc``::

    python main.py source
"""

from __future__ import annotations

from typing import Any

from duplicate_checking import DuplicateChecker
from sourcing.FercCandidateFetcher import FercCandidateFetcher, canonical_dataset_url
from sourcing.SourcingBase import SourcingBase
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


class FercSourcing(SourcingBase):
    """
    Source FERC datasets into Storage from the data-assets catalog.

    Already-sourced landing-page URLs are skipped before insert.
    """

    def __init__(self, *, fetcher: FercCandidateFetcher | None = None) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
        """
        self._fetcher = fetcher or FercCandidateFetcher()

    def run(self, drpid: int) -> None:
        """
        Enumerate FERC catalog datasets and insert new rows into Storage.

        ``Args.num_rows`` limits how many pending datasets are inserted per run.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)
        limit = Args.num_rows
        Logger.info("FERC sourcing: starting catalog enumeration (limit=%s)", limit)
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
        Logger.info(
            "FERC sourcing: %s dataset(s) in catalog, %s already sourced, "
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
                Logger.error("FERC record %s failed: %s", source_url, exc)
                continue
            if index <= 20 or index % 25 == 0 or index == len(batch_rows):
                Logger.info("FERC sourcing progress: %s/%s", index, len(batch_rows))
        remaining = len(pending_rows) - len(batch_rows)
        Logger.info(
            "FERC sourcing complete: %s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s pending for next batch",
            inserted,
            self.format_id_range(assigned_ids),
            failed,
            skipped_dupes,
            remaining,
        )

    def _pending_rows(self, all_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return rows whose landing-page URLs are not yet stored."""
        stored_urls = self._stored_urls()
        pending: list[dict[str, str]] = []
        for row in all_rows:
            url = canonical_dataset_url(row["url"])
            if url and url in stored_urls:
                continue
            pending.append(row)
        return pending

    def _stored_urls(self) -> set[str]:
        """Return canonical FERC dataset URLs already in Storage."""
        stored: set[str] = set()
        for source_url in Storage.list_source_urls():
            url = canonical_dataset_url(source_url)
            if url is not None:
                stored.add(url)
        return stored

    def _storage_fields_from_row(self, row: dict[str, str]) -> dict[str, Any]:
        """Map a candidate row to Storage update fields."""
        return {
            "title": row.get("title", ""),
            "summary": row.get("summary", ""),
            "agency": row.get("agency", ""),
            "office": row.get("office", ""),
            "status": "sourced",
        }
