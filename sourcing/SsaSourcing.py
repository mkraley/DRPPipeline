"""
Social Security Administration sourcing module for DRP Pipeline.

Enumerates public file datasets from the Data.gov catalog (GSA Catalog API)
and creates ``sourced`` storage records. Run via orchestrator when
``Args.source`` is ``ssa``::

    python main.py sourcing
"""

from __future__ import annotations

from typing import Any

from duplicate_checking import DuplicateChecker
from sourcing.SsaCandidateFetcher import SsaCandidateFetcher, slug_from_source_url
from sourcing.SourcingBase import SourcingBase
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


class SsaSourcing(SourcingBase):
    """
    Source SSA datasets into Storage from the Data.gov catalog.

    Already-sourced catalog slugs are skipped before insert.
    """

    def __init__(
        self,
        *,
        fetcher: SsaCandidateFetcher | None = None,
    ) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
        """
        self._fetcher = fetcher or SsaCandidateFetcher()

    def run(self, drpid: int) -> None:
        """
        Enumerate SSA catalog datasets and insert new rows into Storage.

        ``Args.num_rows`` limits how many pending datasets are inserted per run.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)

        limit = Args.num_rows
        Logger.info("SSA sourcing: starting catalog enumeration (limit=%s)", limit)

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
            "SSA sourcing: %s collectible dataset(s) in catalog, %s already sourced, "
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
                Logger.error("SSA record %s failed: %s", source_url, exc)
                continue

            if index <= 20 or index % 25 == 0 or index == len(batch_rows):
                Logger.info("SSA sourcing progress: %s/%s", index, len(batch_rows))

        remaining = len(pending_rows) - len(batch_rows)
        Logger.info(
            "SSA sourcing complete: %s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s pending for next batch",
            inserted,
            self.format_id_range(assigned_ids),
            failed,
            skipped_dupes,
            remaining,
        )

    def _pending_rows(self, all_rows: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return rows whose catalog slugs are not yet stored."""
        stored_slugs = self._stored_slugs()
        pending: list[dict[str, str]] = []
        for row in all_rows:
            slug = row.get("record_id") or slug_from_source_url(row["url"])
            if slug and slug in stored_slugs:
                continue
            pending.append(row)
        return pending

    def _stored_slugs(self) -> set[str]:
        """Parse catalog slugs from stored SSA source URLs."""
        stored: set[str] = set()
        for source_url in Storage.list_source_urls():
            slug = slug_from_source_url(source_url)
            if slug is not None:
                stored.add(slug)
        return stored

    def _storage_fields_from_row(self, row: dict[str, str]) -> dict[str, Any]:
        """Map a candidate row to Storage update fields."""
        return {
            "title": row.get("title", ""),
            "agency": row.get("agency", ""),
            "office": row.get("office", ""),
            "status": "sourced",
        }
