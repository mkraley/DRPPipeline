"""
National Park Service sourcing module for DRP Pipeline.

Walks IRMA DataStore Collection → Program → Project and creates one
``sourced`` Storage row per unique IRMA Project that has public Digital
Files. Run via orchestrator when ``Args.source`` is ``nps``::

    python main.py sourcing --source nps
"""

from __future__ import annotations

from typing import Any

from duplicate_checking import DuplicateChecker
from sourcing.NpsCandidateFetcher import NpsCandidateFetcher
from sourcing.NpsReferenceRules import irma_project_id_from_source_url
from sourcing.SourcingBase import SourcingBase
from storage import Storage
from storage.NpsHierarchyStore import NpsHierarchyStore
from utils.Args import Args
from utils.Logger import Logger


class NpsSourcing(SourcingBase):
    """
    Source NPS IRMA Projects into Storage from Collection 9688.

    Default ``nps_program_id`` is APHN (2310251). Set it to 0 to source
    every Program in the Collection. Already-sourced IRMA Project ids
    are skipped before insert.
    """

    def __init__(
        self,
        *,
        fetcher: NpsCandidateFetcher | None = None,
        hierarchy_store: NpsHierarchyStore | None = None,
    ) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
            hierarchy_store: Extra Program/Product tables (created when omitted).
        """
        self._fetcher = fetcher or NpsCandidateFetcher()
        self._hierarchy_store = hierarchy_store

    def run(self, drpid: int) -> None:
        """
        Enumerate IRMA Projects and insert new rows into Storage.

        ``Args.num_rows`` limits how many pending Projects are inserted per run.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)
        limit = Args.num_rows
        Logger.info("NPS sourcing: starting IRMA enumeration (limit=%s)", limit)
        try:
            all_rows = self._fetcher.list_project_rows()
        finally:
            self._fetcher.close()

        pending_rows = self._pending_rows(all_rows)
        batch_rows = pending_rows[:limit] if limit is not None else pending_rows
        store = self._hierarchy_store or NpsHierarchyStore.from_storage()
        self._insert_batch(all_rows, pending_rows, batch_rows, store)

    def _insert_batch(
        self,
        all_rows: list[dict[str, Any]],
        pending_rows: list[dict[str, Any]],
        batch_rows: list[dict[str, Any]],
        store: NpsHierarchyStore,
    ) -> None:
        """Insert one batch of pending Project rows and log totals."""
        checker = DuplicateChecker()
        inserted = 0
        skipped_dupes = 0
        failed = 0
        assigned_ids: list[int] = []
        Logger.info(
            "NPS sourcing: %s downloadable project(s) in catalog, %s already sourced, "
            "%s pending; processing %s this run (batch limit=%s)",
            len(all_rows),
            len(all_rows) - len(pending_rows),
            len(pending_rows),
            len(batch_rows),
            Args.num_rows,
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
                self._store_hierarchy(store, new_drpid, row)
                inserted += 1
            except Exception as exc:
                failed += 1
                Logger.error("NPS record %s failed: %s", source_url, exc)
                continue
            if index <= 20 or index % 25 == 0 or index == len(batch_rows):
                Logger.info("NPS sourcing progress: %s/%s", index, len(batch_rows))
        remaining = len(pending_rows) - len(batch_rows)
        Logger.info(
            "NPS sourcing complete: %s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s pending for next batch",
            inserted,
            self.format_id_range(assigned_ids),
            failed,
            skipped_dupes,
            remaining,
        )

    def _pending_rows(self, all_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return rows whose IRMA Project ids are not yet stored."""
        stored_ids = self._stored_project_ids()
        pending: list[dict[str, Any]] = []
        for row in all_rows:
            record_id = str(row.get("record_id") or "")
            if not record_id:
                project_id = irma_project_id_from_source_url(str(row.get("url") or ""))
                record_id = str(project_id) if project_id is not None else ""
            if record_id and record_id in stored_ids:
                continue
            pending.append(row)
        return pending

    def _stored_project_ids(self) -> set[str]:
        """Parse IRMA Project ids from stored NPS Profile URLs."""
        stored: set[str] = set()
        for source_url in Storage.list_source_urls():
            project_id = irma_project_id_from_source_url(source_url)
            if project_id is not None:
                stored.add(str(project_id))
        return stored

    def _storage_fields_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Map a candidate row to Storage update fields."""
        fields: dict[str, Any] = {
            "title": row.get("title", ""),
            "agency": row.get("agency", ""),
            "office": row.get("office", ""),
            "summary": row.get("summary", ""),
            "keywords": row.get("keywords", ""),
            "collection_notes": row.get("collection_notes", ""),
            "status": "sourced",
        }
        for key in ("time_start", "time_end", "geographic_coverage"):
            value = row.get(key)
            if value:
                fields[key] = value
        public_files = row.get("public_file_count")
        if public_files is not None and public_files != "":
            fields["num_files"] = int(public_files)
        return fields

    def _store_hierarchy(
        self,
        store: NpsHierarchyStore,
        drpid: int,
        row: dict[str, Any],
    ) -> None:
        """Write nps_projects and nps_products rows for one sourced Project."""
        project_id = int(row["irma_project_id"])
        store.upsert_project(
            {
                "irma_project_id": project_id,
                "drpid": drpid,
                "irma_collection_id": int(row["irma_collection_id"]),
                "irma_program_id": int(row["irma_program_id"]),
                "collection_title": row.get("collection_title", ""),
                "program_title": row.get("program_title", ""),
                "project_title": row.get("project_title", ""),
                "breadcrumb": row.get("breadcrumb", ""),
                "public_file_count": int(row.get("public_file_count") or 0),
                "product_count": len(row.get("products") or []),
            }
        )
        products = []
        for product in row.get("products") or []:
            products.append({**product, "drpid": drpid})
        store.replace_products(project_id, products)
