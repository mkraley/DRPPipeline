"""
Verify uploaded projects by comparing database inventory to DataLumos view pages.

For each ``updated_inventory`` project, locates the matching Google Sheet row,
opens the Download Location URL, and checks file count and total size against
``num_files`` and ``file_size`` in Storage.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from utils.Args import Args
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
    format_verify_success_message,
    set_records_per_page,
    verify_upload_counts,
)


class UploadVerifier:
    """
    Verify that DataLumos published pages match collected inventory metadata.

    Implements ModuleProtocol. Processes projects with status ``updated_inventory``.
    Logs a one-line info summary on success; logs errors on failure.
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
            Logger.error(f"DRPID {drpid}: project not found in database")
            return

        source_url = (get_field(project, "source_url") or "").strip()
        if not source_url:
            Logger.error(f"DRPID {drpid}: missing source_url in database")
            return

        sheet_row = self._sheet_row_for_url(source_url)
        if sheet_row is None:
            Logger.error(
                f"DRPID {drpid}: source_url not found on inventory sheet: {source_url}"
            )
            return

        download_url = pick_sheet_col(sheet_row, "Download Location").strip()
        if not download_url:
            Logger.error(
                f"DRPID {drpid}: Download Location empty on inventory sheet for {source_url}"
            )
            return

        page_stats = self._fetch_page_stats(download_url)
        db_num_files = project.get("num_files")
        if db_num_files is not None:
            db_num_files = int(db_num_files)
        db_file_size = get_field(project, "file_size")

        errors = verify_upload_counts(db_num_files, db_file_size, page_stats)
        if errors:
            for message in errors:
                Logger.error(f"DRPID {drpid}: {message}")
            return
        Logger.info(
            f"DRPID {drpid}: OK — {format_verify_success_message(db_num_files, db_file_size, page_stats)}"
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
