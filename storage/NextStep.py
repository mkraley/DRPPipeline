"""
Choose the next pipeline module for a project status.

Terminal statuses return None. Unrecognized or manual-hold statuses return "?".
"""

from __future__ import annotations

from collectors.GlobusFileManagerUrl import GlobusFileManagerUrl
from publisher.sheet_only_status import is_collector_hold_status
from utils.Errors import normalize_status_hyphens
from utils.inventory_status import (
    STATUS_COLLECTED_LARGE,
    STATUS_COLLECTED_XLARGE,
    STATUS_DOWNLOADED,
    STATUS_FINISH_WAIT,
    STATUS_RESIZE_WAIT,
    STATUS_RESIZED,
    STATUS_UPLOADED_LARGE,
    STATUS_UPLOADED_XLARGE,
)

# Status value -> next module, "?" when a person must decide, None when finished.
_NEXT_BY_STATUS: dict[str, str | None] = {
    "sourced": "collect",
    "not_found": "publish",
    "dupe_in_DL": None,
    "collected": "upload",
    "collected - large file": "upload",
    STATUS_COLLECTED_LARGE: "upload",
    STATUS_COLLECTED_XLARGE: "upload",
    "collected - file pending": "?",
    "no_links": "publish",
    "no dataset": "publish",
    "gigantic upload": "publish",
    "needs scripting": "publish",
    "uploaded": "publish",
    "uploaded - large file": "upload_large_files",
    "uploaded - expanded": "upload_large_files",
    STATUS_UPLOADED_LARGE: "resume_download",
    STATUS_UPLOADED_XLARGE: STATUS_RESIZE_WAIT,
    STATUS_RESIZE_WAIT: STATUS_RESIZED,
    STATUS_RESIZED: "resume_download",
    STATUS_DOWNLOADED: "resume_upload",
    STATUS_FINISH_WAIT: "uploaded",
    "re-uploaded": "republish",
    "published": "publish",
    "updated_inventory": "verify_upload",
    "updated_not_found": None,
    "updated_no_links": None,
    "updated_no_dataset": None,
    "updated_gigantic_upload": None,
    "updated_needs_scripting": None,
    "updated_collector_hold": None,
    "error": "?",
}

_EXTERNAL_ARCHIVE = "collected - external archive"
_COMPACT_TO_CANONICAL: dict[str, str] = {
    normalize_status_hyphens(name): name for name in _NEXT_BY_STATUS
}


def next_step_for_status(
    status: str | None,
    status_notes: str | None = None,
) -> str | None:
    """
    Return the module that should run next for this status.

    Args:
        status: Current projects.status value.
        status_notes: Used to tell Globus external archives from other holds.

    Returns:
        A module name, "?" when the next module is not clear, or None when
        no further module should run.
    """
    if status is None or not str(status).strip():
        return "?"
    key = _status_without_error(str(status).strip())
    if _is_hold(key):
        return "publish"
    if key == _EXTERNAL_ARCHIVE:
        return _external_archive_next_step(status_notes)
    if key in _NEXT_BY_STATUS:
        return _NEXT_BY_STATUS[key]
    return "?"


def _status_without_error(status: str) -> str:
    """Map compact error statuses back to the status work started from."""
    normalized = normalize_status_hyphens(status)
    if normalized.endswith("-error") and normalized != "error":
        normalized = normalized[: -len("-error")]
    return _COMPACT_TO_CANONICAL.get(normalized, status)


def _is_hold(status: str) -> bool:
    """Return True for interactive collector-hold statuses, including error form."""
    if is_collector_hold_status(status):
        return True
    compact = normalize_status_hyphens(status)
    return compact.startswith("collector_hold-") or compact.startswith("collector-hold-")


def _external_archive_next_step(status_notes: str | None) -> str:
    """Return the Globus collector, or '?' when the archive host is unknown."""
    if GlobusFileManagerUrl.from_status_notes(status_notes) is not None:
        return "collect_adc_globus"
    return "?"
