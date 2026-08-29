"""
Shared collector status constants and Storage merge helpers.
"""

from __future__ import annotations

from typing import Any, FrozenSet

from storage import Storage
from utils.Errors import derive_error_status, is_error_status

STATUS_COLLECTED = "collected"
STATUS_COLLECTED_LARGE_FILE = "collected - large file"
STATUS_COLLECTED_EXTERNAL_ARCHIVE = "collected - external archive"
STATUS_NOT_FOUND = "not_found"
MAX_DOWNLOAD_BYTES = 1 * 1024**3


def large_file_skip_note(filename: str, file_url: str, size_bytes: int) -> str:
    """
    Build a status_notes line for a file skipped due to size.

    Args:
        filename: Catalog or download filename.
        file_url: Manual download URL.
        size_bytes: Catalog-reported size in bytes.

    Returns:
        Human-readable skip note for status_notes.
    """
    from utils.file_utils import format_file_size

    return (
        f"Skipped download (>1GB): {filename} ({format_file_size(size_bytes)}) - "
        f"download manually: {file_url}"
    )


def resolve_standard_collected_status(
    result: dict[str, Any],
    *,
    previous_status: str | None,
) -> None:
    """
    Set ``result['status']`` for standard Playwright/API collectors.

    Preserves normalized error statuses; defaults to ``collected`` when a
    folder path exists and no status was set.

    Args:
        result: Mutable collection result dict.
        previous_status: Current Storage status before merge.
    """
    if previous_status and is_error_status(previous_status):
        result["status"] = derive_error_status(previous_status)
    elif not result.get("status") and result.get("folder_path"):
        result["status"] = STATUS_COLLECTED


def resolve_inventory_collected_status(
    result: dict[str, Any],
    *,
    has_errors: bool,
) -> None:
    """
    Set ``result['status']`` for inventory-style collectors (ADC, USFS).

    Pops ``_skipped_large_file`` and ``_external_archive`` flags from ``result``.

    Args:
        result: Mutable collection result dict.
        has_errors: Whether Storage already has a non-empty errors field.
    """
    skipped_large = bool(result.pop("_skipped_large_file", False))
    external_archive = bool(result.pop("_external_archive", False))
    if has_errors:
        result.pop("status", None)
    elif result.get("folder_path"):
        if skipped_large:
            result["status"] = STATUS_COLLECTED_LARGE_FILE
        elif external_archive:
            result["status"] = STATUS_COLLECTED_EXTERNAL_ARCHIVE
        else:
            result["status"] = STATUS_COLLECTED


def merge_result_to_storage(
    drpid: int,
    result: dict[str, Any],
    *,
    status_mode: str = "standard",
    skip_keys: FrozenSet[str] = frozenset(),
) -> None:
    """
    Apply a collection result dict to Storage.

    Args:
        drpid: Project DRPID.
        result: Fields to merge (mutated when ``status_mode`` is ``inventory``).
        status_mode: ``standard`` or ``inventory`` status resolution.
        skip_keys: Result keys to omit from Storage update.
    """
    current = Storage.get(drpid) or {}
    previous_status = current.get("status")

    if status_mode == "notes_only":
        pass
    elif status_mode == "inventory":
        has_errors = bool(str(current.get("errors") or "").strip())
        resolve_inventory_collected_status(result, has_errors=has_errors)
    else:
        resolve_standard_collected_status(result, previous_status=previous_status)

    update_fields: dict[str, Any] = {}
    for key, value in result.items():
        if key in skip_keys:
            continue
        if value is None:
            continue
        if value == "":
            continue
        update_fields[key] = value

    if update_fields:
        Storage.update_record(drpid, update_fields)
