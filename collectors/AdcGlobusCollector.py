"""
Supplemental Globus collector for ADC external-archive datasets.

Runs after ``adc_collector`` when status is ``collected - external archive`` and
``status_notes`` contains a Globus File Manager URL. Transfers files from the
shared Globus endpoint into the existing DRP folder via Globus Connect Personal.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from collectors.GlobusFileManagerUrl import GlobusFileManagerUrl
from collectors.GlobusTransferService import GlobusTransferService
from storage import Storage
from collectors.GlobusConfig import build_transfer_service
from utils.Errors import record_error, record_warning
from utils.Logger import Logger
from utils.file_utils import folder_extensions_and_size, format_file_size

STATUS_EXTERNAL_ARCHIVE = "collected - external archive"
STATUS_COLLECTED = "collected"
_SKIP_LOG = "Skipping DRPID %s: not a Globus external archive"


class AdcGlobusCollector:
    """Transfer Globus-hosted ADC datasets into existing project folders."""

    def run(self, drpid: int) -> None:
        """
        Run Globus supplemental collection for one project.

        Args:
            drpid: DRPID with ``collected - external archive`` and Globus URL.
        """
        record = Storage.get(drpid)
        if record is None:
            record_error(drpid, f"Project record not found for DRPID: {drpid}", update_storage=False)
            return

        if record.get("status") != STATUS_EXTERNAL_ARCHIVE:
            Logger.info("DRPID %s status is %r; Globus collector expects %r", drpid, record.get("status"), STATUS_EXTERNAL_ARCHIVE)
            return

        globus_url = GlobusFileManagerUrl.from_status_notes(record.get("status_notes"))
        if globus_url is None:
            Logger.info(_SKIP_LOG, drpid)
            return

        folder_path = record.get("folder_path")
        if not folder_path:
            record_error(drpid, f"Missing folder_path for DRPID {drpid}")
            return

        try:
            service = self._build_transfer_service()
            result = self._collect(drpid, globus_url, Path(folder_path), service)
            self._update_storage(drpid, result)
        except Exception as exc:
            record_error(drpid, f"Globus collection failed for DRPID {drpid}: {exc}")

    def _collect(
        self,
        drpid: int,
        globus_url: GlobusFileManagerUrl,
        folder_path: Path,
        service: GlobusTransferService,
    ) -> dict[str, Any]:
        """
        Submit and wait for a Globus directory transfer.

        Args:
            drpid: Project DRPID.
            globus_url: Parsed Globus File Manager URL.
            folder_path: Local project folder (mapped on destination endpoint).

        Returns:
            Storage update fields on success.
        """
        entries = self._list_source(service, globus_url)
        if not entries:
            record_warning(drpid, f"Globus source path is empty: {globus_url.origin_path}")

        rel_dest = folder_path.name
        task_id = service.transfer_directory(
            source_endpoint_id=globus_url.origin_id,
            source_path=globus_url.origin_path,
            destination_relative_path=rel_dest,
            label=f"DRP{drpid:06d} ADC Globus",
        )
        service.wait_for_task(task_id)

        extensions, total_bytes, num_files = folder_extensions_and_size(folder_path)
        note_line = f"Globus transfer complete (task_id={task_id})"
        prior_notes = (Storage.get(drpid) or {}).get("status_notes") or ""
        status_notes = f"{prior_notes}\n{note_line}".strip() if prior_notes else note_line

        Logger.info(
            "Globus collection complete for DRPID %s: %s files, %s",
            drpid,
            num_files,
            format_file_size(total_bytes),
        )
        return {
            "folder_path": str(folder_path),
            "num_files": num_files,
            "file_size": format_file_size(total_bytes),
            "extensions": ", ".join(extensions),
            "download_date": date.today().isoformat(),
            "status_notes": status_notes,
            "status": STATUS_COLLECTED,
        }

    def _list_source(
        self,
        service: GlobusTransferService,
        globus_url: GlobusFileManagerUrl,
    ) -> list[dict[str, Any]]:
        """List source directory entries for logging."""
        entries = service.list_source_entries(
            globus_url.origin_id,
            globus_url.origin_path,
        )
        Logger.info(
            "Globus source %s:%s has %s entries",
            globus_url.origin_id,
            globus_url.origin_path,
            len(entries),
        )
        return entries

    def _build_transfer_service(self):
        """Construct GlobusTransferService from Args configuration."""
        return build_transfer_service(require_destination=True)

    def _update_storage(self, drpid: int, result: dict[str, Any]) -> None:
        """Persist successful Globus collection results."""
        current = Storage.get(drpid) or {}
        if (current.get("errors") or "").strip():
            result.pop("status", None)
        update_fields = {
            key: value
            for key, value in result.items()
            if value is not None and value != ""
        }
        if update_fields:
            Storage.update_record(drpid, update_fields)


def is_globus_external_archive(project: dict[str, Any]) -> bool:
    """
    Return True when a project is a Globus external-archive candidate.

    Args:
        project: Full Storage project row.

    Returns:
        True if status and status_notes indicate a Globus File Manager link.
    """
    if project.get("status") != STATUS_EXTERNAL_ARCHIVE:
        return False
    return GlobusFileManagerUrl.from_status_notes(project.get("status_notes")) is not None
