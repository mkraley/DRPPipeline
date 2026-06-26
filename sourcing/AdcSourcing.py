"""
Ag Data Commons (ADC) sourcing module for DRP Pipeline.

Enumerates ADC datasets via the public Figshare API (no portal WAF), builds file
summaries (including Dryad/Zenodo expansion when applicable), and creates
``sourced`` storage records. Run via orchestrator::

    python main.py adc_sourcing
"""

from __future__ import annotations

import time
from typing import Any

import requests

from duplicate_checking import DuplicateChecker
from sourcing.AdcApiClient import article_id_from_source_url
from sourcing.AdcCandidateFetcher import AdcCandidateFetcher
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

DEFAULT_FORBIDDEN_RETRIES = 3
FORBIDDEN_BACKOFF_SECONDS = 2.0


class AdcSourcing:
    """
    Source Ag Data Commons datasets into Storage using the Figshare public API.

    Unlike spreadsheet :class:`Sourcing`, URL availability is not re-checked
    (metadata already comes from ``api.figshare.com``). Duplicate URLs are skipped.
    """

    def __init__(
        self,
        *,
        fetcher: AdcCandidateFetcher | None = None,
        request_delay: float | None = None,
        forbidden_retries: int = DEFAULT_FORBIDDEN_RETRIES,
        forbidden_backoff: float = FORBIDDEN_BACKOFF_SECONDS,
    ) -> None:
        """
        Initialize the sourcing module.

        Args:
            fetcher: Candidate fetcher (created when omitted).
            request_delay: Seconds between per-dataset API calls; defaults to Args
                ``adc_request_delay`` or 0.1.
            forbidden_retries: Retries when Figshare returns HTTP 403.
            forbidden_backoff: Base seconds for exponential backoff on 403 retries.
        """
        self._fetcher = fetcher or AdcCandidateFetcher()
        default_delay = float(getattr(Args, "adc_request_delay", 0.1) or 0.1)
        self._request_delay = request_delay if request_delay is not None else default_delay
        self._forbidden_retries = forbidden_retries
        self._forbidden_backoff = forbidden_backoff

    def run(self, drpid: int) -> None:
        """
        Enumerate ADC datasets and insert new rows into Storage.

        Already-sourced article IDs are skipped before fetch. ``Args.num_rows``
        limits how many pending articles are processed per run (for rate-limit recovery).

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        if drpid != -1:
            Logger.warning(
                "AdcSourcing ignores DRPID %s; batch enumeration uses run(-1).",
                drpid,
            )

        limit = Args.num_rows
        Logger.info(
            "ADC sourcing: starting enumeration (limit=%s)",
            limit,
        )
        all_article_ids = self._fetcher.list_article_ids(limit=None)
        pending_ids = self._pending_article_ids(all_article_ids)
        batch_ids = pending_ids[:limit] if limit is not None else pending_ids
        checker = DuplicateChecker()
        inserted = 0
        skipped_dupes = 0
        skipped_invalid = 0
        failed = 0
        assigned_ids: list[int] = []

        Logger.info(
            "ADC sourcing: %s catalog ID(s), %s already sourced, %s pending; "
            "processing %s this run (batch limit=%s)",
            len(all_article_ids),
            len(all_article_ids) - len(pending_ids),
            len(pending_ids),
            len(batch_ids),
            limit,
        )

        for index, article_id in enumerate(batch_ids, 1):
            try:
                article = self._fetch_article_with_retry(article_id)
                row = self._fetcher.build_candidate_row(article, include_inventory=True)
            except Exception as exc:
                failed += 1
                Logger.error("ADC article %s failed: %s", article_id, exc)
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

            if index <= 20 or index % 25 == 0 or index == len(batch_ids):
                Logger.info("ADC sourcing progress: %s/%s", index, len(batch_ids))

            if self._request_delay > 0:
                time.sleep(self._request_delay)

        id_range = ""
        if assigned_ids:
            low, high = min(assigned_ids), max(assigned_ids)
            id_range = f" (DRPID: {low})" if low == high else f" (DRPIDs: {low}-{high})"

        remaining = len(pending_ids) - len(batch_ids)
        Logger.info(
            "ADC sourcing complete: %s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s non-ADC article(s) skipped, %s pending for next batch",
            inserted,
            id_range,
            failed,
            skipped_dupes,
            skipped_invalid,
            remaining,
        )

    def _pending_article_ids(self, all_article_ids: list[int]) -> list[int]:
        """Return catalog IDs not yet represented in Storage by portal URL."""
        stored_ids = self._stored_article_ids()
        return [article_id for article_id in all_article_ids if article_id not in stored_ids]

    def _stored_article_ids(self) -> set[int]:
        """Parse Figshare article IDs from every stored ADC source URL."""
        stored: set[int] = set()
        for source_url in Storage.list_source_urls():
            article_id = article_id_from_source_url(source_url)
            if article_id is not None:
                stored.add(article_id)
        return stored

    def _fetch_article_with_retry(self, article_id: int) -> dict[str, Any]:
        """
        Fetch Figshare metadata, retrying HTTP 403 with exponential backoff.

        Args:
            article_id: Figshare article ID.

        Returns:
            Article JSON document.

        Raises:
            requests.HTTPError: When fetch fails after retries.
        """
        last_error: Exception | None = None
        attempts = self._forbidden_retries + 1
        for attempt in range(attempts):
            try:
                return self._fetcher.fetch_article(article_id)
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code != 403 or attempt >= attempts - 1:
                    raise
                wait_seconds = self._forbidden_backoff * (2 ** attempt)
                Logger.warning(
                    "ADC article %s returned 403; retry %s/%s in %.1fs",
                    article_id,
                    attempt + 1,
                    self._forbidden_retries,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to fetch ADC article {article_id}")

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
