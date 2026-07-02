"""
Survey Globus external-archive datasets for remote file counts and sizes.

Runs after ``adc_collector`` when status is ``collected - external archive`` and
``status_notes`` contains a Globus File Manager URL. Does not download data;
writes inventory totals into ``status_notes``.
"""

from __future__ import annotations

from typing import Any

from collectors.AdcGlobusCollector import is_globus_external_archive
from collectors.GlobusConfig import build_transfer_service
from collectors.GlobusFileManagerUrl import GlobusFileManagerUrl
from collectors.GlobusSurveyNotes import has_survey_notes, upsert_survey_line
from storage import Storage
from utils.Args import Args
from utils.Errors import record_error
from utils.Logger import Logger
from utils.file_utils import format_file_size

STATUS_EXTERNAL_ARCHIVE = "collected - external archive"
_SKIP_LOG = "Skipping DRPID %s: not a Globus external archive"
_ALREADY_SURVEYED = "Skipping DRPID %s: Globus inventory already in status_notes"


class AdcGlobusSurvey:
    """Survey remote Globus-hosted ADC datasets without transferring files."""

    def run(self, drpid: int) -> None:
        """
        Inventory one Globus external-archive project and update status_notes.

        Args:
            drpid: DRPID with ``collected - external archive`` and Globus URL.
        """
        record = Storage.get(drpid)
        if record is None:
            record_error(drpid, f"Project record not found for DRPID: {drpid}", update_storage=False)
            return

        if record.get("status") != STATUS_EXTERNAL_ARCHIVE:
            Logger.info(
                "DRPID %s status is %r; Globus survey expects %r",
                drpid,
                record.get("status"),
                STATUS_EXTERNAL_ARCHIVE,
            )
            return

        globus_url = GlobusFileManagerUrl.from_status_notes(record.get("status_notes"))
        if globus_url is None:
            Logger.info(_SKIP_LOG, drpid)
            return

        status_notes = record.get("status_notes") or ""
        if has_survey_notes(status_notes) and not bool(getattr(Args, "globus_survey_resurvey", False)):
            Logger.info(_ALREADY_SURVEYED, drpid)
            return

        try:
            service = build_transfer_service(require_destination=False)
            summary = service.summarize_remote_path(
                globus_url.origin_id,
                globus_url.origin_path,
            )
            updated_notes = upsert_survey_line(status_notes, summary)
            Storage.update_record(drpid, {"status_notes": updated_notes})
            Logger.info(
                "Globus survey complete for DRPID %s: %s files, %s",
                drpid,
                summary.file_count,
                format_file_size(summary.total_bytes),
            )
        except Exception as exc:
            record_error(drpid, f"Globus survey failed for DRPID {drpid}: {exc}")


__all__ = ["AdcGlobusSurvey", "is_globus_external_archive"]
