"""
Verify uploaded projects by comparing database inventory to DataLumos view pages.

For each ``updated_inventory`` (or previously errored ``updated_inventory-error``)
project, locates the matching Google Sheet row, opens the Download Location URL,
and checks file count and total size against ``num_files`` and ``file_size`` in
Storage.

When DataLumos has fewer files than the database, attempts to re-download and
re-upload missing catalog publication files, then sets status ``re-uploaded``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
from utils.Errors import is_error_status, record_error
from utils.Logger import Logger
from utils.inventory_sheet_reconcile import (
    build_sheet_url_index,
    fetch_inventory_sheet_rows,
    normalize_url,
    pick_sheet_col,
)
from utils.project_utils import get_field
from verify.DatalumosViewFileStats import (
    DatalumosViewFileStats,
    format_verify_comparison,
    format_verify_success_message,
    set_records_per_page,
    verify_upload_counts,
)
from verify.MissingFileRepair import (
    STATUS_RE_UPLOADED,
    MissingFileRepair,
    should_attempt_missing_file_repair,
)


STATUS_UPDATED_INVENTORY = "updated_inventory"


class UploadVerifier:
    """
    Verify that DataLumos published pages match collected inventory metadata.

    Implements ModuleProtocol. Processes projects with status ``updated_inventory``
    or ``updated_inventory-error`` (retry of a previously failed verification).
    Logs a one-line info summary on success. On failure, records project errors via
    ``record_error`` (status becomes ``updated_inventory-error``).
    On successful missing-file repair, sets status to ``re-uploaded``.
    When a previously errored project now verifies clean, resets status to
    ``updated_inventory`` and clears the errors field.
    """

    _sheet_index: Optional[Dict[str, Dict[str, str]]] = None

    def __init__(self) -> None:
        """Initialize browser session and lazy sheet cache."""
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        """
        Verify upload inventory for a single project.

        Args:
            drpid: DRPID of the project to verify.
        """
        project = Storage.get(drpid)
        if project is None:
            record_error(
                drpid,
                f"DRPID {drpid}: project not found in database",
                update_storage=False,
            )
            return

        source_url = (get_field(project, "source_url") or "").strip()
        if not source_url:
            record_error(drpid, f"DRPID {drpid}: missing source_url in database")
            return

        sheet_row = self._sheet_row_for_url(source_url)
        if sheet_row is None:
            record_error(
                drpid,
                f"DRPID {drpid}: source_url not found on inventory sheet: {source_url}",
            )
            return

        download_url = pick_sheet_col(sheet_row, "Download Location").strip()
        if not download_url:
            record_error(
                drpid,
                f"DRPID {drpid}: Download Location empty on inventory sheet "
                f"for {source_url}",
            )
            return

        page_stats = self._fetch_page_stats(download_url)
        db_num_files = project.get("num_files")
        if db_num_files is not None:
            db_num_files = int(db_num_files)
        db_file_size = get_field(project, "file_size")
        datalumos_id = (get_field(project, "datalumos_id") or "").strip() or "?"

        errors = verify_upload_counts(db_num_files, db_file_size, page_stats)
        if not errors:
            Logger.info(
                f"DRPID {drpid}: OK — "
                f"{format_verify_success_message(db_num_files, db_file_size, page_stats)}"
            )
            self._reset_error_status_if_needed(drpid, project)
            return

        comparison = format_verify_comparison(
            db_num_files, db_file_size, page_stats
        )
        Logger.info(
            f"DRPID {drpid} datalumos_id={datalumos_id}: mismatch — {comparison}"
        )

        if should_attempt_missing_file_repair(db_num_files, page_stats):
            if self._try_repair_missing_files(drpid, project, page_stats, datalumos_id):
                return

        for message in errors:
            record_error(
                drpid,
                f"DRPID {drpid} datalumos_id={datalumos_id}: {message}",
            )

    def _try_repair_missing_files(
        self,
        drpid: int,
        project: Dict[str, Any],
        page_stats: DatalumosViewFileStats,
        datalumos_id: str,
    ) -> bool:
        """
        Attempt missing-file repair; on success set status ``re-uploaded``.

        Args:
            drpid: Project DRPID.
            project: Storage project record.
            page_stats: DataLumos view stats.
            datalumos_id: DataLumos id for log messages.

        Returns:
            True when repair succeeded and status was updated.
        """
        try:
            repaired = MissingFileRepair(self._session).repair(
                drpid, project, page_stats
            )
        except Exception as exc:
            record_error(
                drpid,
                f"DRPID {drpid} datalumos_id={datalumos_id}: "
                f"missing-file repair failed: {exc}",
            )
            return False
        if not repaired:
            return False
        # Clear stale errors so the republisher will pick the project up.
        Storage.update_record(drpid, {"status": STATUS_RE_UPLOADED, "errors": None})
        Logger.info(
            f"DRPID {drpid} datalumos_id={datalumos_id}: "
            f"re-uploaded missing file(s); status={STATUS_RE_UPLOADED}"
        )
        return True

    def _reset_error_status_if_needed(
        self, drpid: int, project: Dict[str, Any]
    ) -> None:
        """
        Reset a previously errored project once verification passes.

        For a project retried from ``updated_inventory-error``, restore status
        ``updated_inventory`` and clear the errors field so downstream modules
        (e.g. republisher) treat it as eligible again.

        Args:
            drpid: Project DRPID.
            project: Storage project record as loaded at the start of run().
        """
        status = (get_field(project, "status") or "").strip()
        if not is_error_status(status):
            return
        Storage.update_record(
            drpid, {"status": STATUS_UPDATED_INVENTORY, "errors": None}
        )
        Logger.info(
            f"DRPID {drpid}: verification passed on retry; "
            f"status reset to {STATUS_UPDATED_INVENTORY} and errors cleared"
        )

    def _sheet_row_for_url(self, source_url: str) -> Optional[Dict[str, str]]:
        """
        Return the inventory sheet row matching ``source_url``.

        Args:
            source_url: Project source URL from Storage.

        Returns:
            Sheet row dict, or None when not found.
        """
        index = self._ensure_sheet_index()
        return index.get(normalize_url(source_url))

    def _ensure_sheet_index(self) -> Dict[str, Dict[str, str]]:
        """
        Load and cache the inventory sheet indexed by normalized URL.

        Returns:
            Mapping of normalized URL to sheet row.
        """
        if UploadVerifier._sheet_index is not None:
            return UploadVerifier._sheet_index

        sheet_name = (getattr(Args, "google_sheet_name", None) or "").strip()
        if not Args.google_sheet_id or not sheet_name:
            raise RuntimeError(
                "verify_upload requires google_sheet_id and google_sheet_name in config"
            )
        rows = fetch_inventory_sheet_rows(sheet_name)
        UploadVerifier._sheet_index = build_sheet_url_index(rows)
        return UploadVerifier._sheet_index

    def _fetch_page_stats(self, download_url: str) -> DatalumosViewFileStats:
        """
        Open a DataLumos view page and extract file statistics.

        Args:
            download_url: Published project view URL from the inventory sheet.

        Returns:
            Parsed page stats, with ``error`` set when the page cannot be read.
        """
        page = self._session.ensure_browser()
        try:
            self._session.ensure_authenticated()
            response = page.goto(
                download_url,
                wait_until="domcontentloaded",
                timeout=int(Args.upload_timeout),
            )
            if response is not None and response.status >= 400:
                return DatalumosViewFileStats(error=f"http_{response.status}")
            page.wait_for_load_state("networkidle", timeout=120000)
            from upload.DataLumosAuthenticator import wait_for_human_verification

            wait_for_human_verification(page, timeout=60000)
            set_records_per_page(page)
            return DatalumosViewFileStats.from_page(page)
        except PlaywrightTimeoutError:
            return DatalumosViewFileStats(error="page_load_timeout")
        except Exception as exc:
            return DatalumosViewFileStats(error=str(exc))
