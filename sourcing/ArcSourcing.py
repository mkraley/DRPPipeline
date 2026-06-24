"""
Ag Data Commons (ARC) sourcing module for DRP Pipeline.

Enumerates ARC datasets via the public Figshare API (no portal WAF), builds file
summaries (including Dryad/Zenodo expansion when applicable), and creates
``sourced`` storage records. Run via orchestrator::

    python main.py arc_sourcing
"""

from __future__ import annotations

import time
from typing import Any

from duplicate_checking import DuplicateChecker
from sourcing.ArcCandidateFetcher import ArcCandidateFetcher
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger


class ArcSourcing:
    """
    Source Ag Data Commons datasets into Storage using the Figshare public API.

    Unlike spreadsheet :class:`Sourcing`, URL availability is not re-checked
    (metadata already comes from ``api.figshare.com``). Duplicate URLs are skipped.
    """

    def __init__(
        self,
        *,
        fetcher: ArcCandidateFetcher | None = None,
        request_delay: float | None = None,
    ) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
            request_delay: Seconds between per-dataset API calls; defaults to Args
                ``arc_request_delay`` or 0.1.
        """
        self._fetcher = fetcher or ArcCandidateFetcher()
        default_delay = float(getattr(Args, "arc_request_delay", 0.1) or 0.1)
        self._request_delay = request_delay if request_delay is not None else default_delay

    def run(self, drpid: int) -> None:
        """
        Enumerate ARC datasets and insert new rows into Storage.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        if drpid != -1:
            Logger.warning(
                "ArcSourcing ignores DRPID %s; batch enumeration uses run(-1).",
                drpid,
            )

        limit = Args.num_rows
        Logger.info(
            "ARC sourcing: starting enumeration (limit=%s)",
            limit,
        )
        article_ids = self._fetcher.list_article_ids(limit=limit)
        checker = DuplicateChecker()
        inserted = 0
        skipped_dupes = 0
        skipped_invalid = 0
        assigned_ids: list[int] = []

        Logger.info(
            "ARC sourcing: processing %s dataset(s) (limit=%s)",
            len(article_ids),
            limit,
        )

        for index, article_id in enumerate(article_ids, 1):
            try:
                article = self._fetcher.fetch_article(article_id)
                row = self._fetcher.build_candidate_row(article, include_inventory=True)
            except Exception as exc:
                Logger.error("ARC article %s failed: %s", article_id, exc)
                continue

            if row is None:
                skipped_invalid += 1
                continue

            source_url = row["url"]
            if checker.exists_in_storage(source_url):
                skipped_dupes += 1
                Logger.error(
                    "Duplicate source URL already in storage, skipping (no row created): %s",
                    source_url,
                )
                continue

            new_drpid = Storage.create_record(source_url)
            assigned_ids.append(new_drpid)
            update_fields = self._storage_fields_from_row(row)
            Storage.update_record(new_drpid, update_fields)
            inserted += 1

            if index <= 20 or index % 25 == 0 or index == len(article_ids):
                Logger.info("ARC sourcing progress: %s/%s", index, len(article_ids))

            if self._request_delay > 0:
                time.sleep(self._request_delay)

        id_range = ""
        if assigned_ids:
            low, high = min(assigned_ids), max(assigned_ids)
            id_range = f" (DRPID: {low})" if low == high else f" (DRPIDs: {low}-{high})"

        Logger.info(
            "ARC sourcing complete: %s inserted%s, %s duplicate(s) skipped, "
            "%s non-ARC article(s) skipped",
            inserted,
            id_range,
            skipped_dupes,
            skipped_invalid,
        )

    def _storage_fields_from_row(self, row: dict[str, str]) -> dict[str, Any]:
        """Map a candidate row to Storage update fields."""
        fields: dict[str, Any] = {
            "title": row.get("title", ""),
            "agency": row.get("agency", ""),
            "office": row.get("office", ""),
            "status": "sourced",
        }
        for key in ("num_files", "file_size", "extensions"):
            if row.get(key):
                if key == "num_files":
                    fields[key] = int(row[key])  # type: ignore[arg-type]
                else:
                    fields[key] = row[key]
        return fields
