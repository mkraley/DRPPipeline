"""
Resolve sheet-only publisher status configs (skips and collector holds).
"""

from __future__ import annotations

from typing import Optional, Tuple

# input status -> (notes, success status, download possible)
SHEET_ONLY_STATUS_CONFIG: dict[str, tuple[str, str, str]] = {
    "not_found": ("Not found", "updated_not_found", "N"),
    "no_links": ("No live links", "updated_no_links", "N"),
    "no dataset": ("no dataset", "updated_no_dataset", "?"),
    "gigantic upload": ("gigantic upload", "updated_gigantic_upload", "?"),
    "needs scripting": ("needs scripting", "updated_needs_scripting", "?"),
}

# Interactive collector hold: ``collector_hold - {reason}`` (legacy: ``collector hold - ``)
COLLECTOR_HOLD_PREFIXES: tuple[str, ...] = (
    "collector_hold - ",
    "collector hold - ",
)

STATUS_UPDATED_COLLECTOR_HOLD = "updated_collector_hold"
COLLECTOR_HOLD_DOWNLOAD_POSSIBLE = "?"

# Sheet-only statuses that update Notes/metadata but must not set Claimed.
SHEET_ONLY_SKIP_CLAIMED_STATUSES: frozenset[str] = frozenset({
    "gigantic upload",
    "needs scripting",
})


def collector_hold_reason(status: str | None) -> Optional[str]:
    """
    Return the reason text after a collector-hold prefix, or None if not a hold.

    Args:
        status: Project status (e.g. ``collector_hold - needs login``).

    Returns:
        The ``xxx`` reason, or None when status is not a collector hold.
    """
    raw = (status or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    for prefix in COLLECTOR_HOLD_PREFIXES:
        if lower.startswith(prefix):
            return raw[len(prefix) :].strip()
    return None


def is_collector_hold_status(status: str | None) -> bool:
    """Return True when status is ``collector_hold - …`` (or legacy spelling)."""
    return collector_hold_reason(status) is not None


def should_write_claimed_for_sheet_only(status: str | None) -> bool:
    """
    Return whether sheet-only publish should set the Claimed column.

    ``gigantic upload`` and ``needs scripting`` leave Claimed unchanged so others
    can pick up the row; other sheet-only paths still claim with ``google_username``.
    """
    key = (status or "").strip().lower()
    return key not in SHEET_ONLY_SKIP_CLAIMED_STATUSES


def resolve_sheet_only_config(
    status: str | None,
) -> Optional[Tuple[str, str, str]]:
    """
    Map a project status to sheet-only publish config.

    Returns:
        ``(notes_value, success_status, download_possible)`` or None when the
        status is not a sheet-only publisher path.
    """
    key = (status or "").strip().lower()
    if key in SHEET_ONLY_STATUS_CONFIG:
        return SHEET_ONLY_STATUS_CONFIG[key]

    reason = collector_hold_reason(status)
    if reason is None:
        return None
    notes = reason if reason else "collector hold"
    return (notes, STATUS_UPDATED_COLLECTOR_HOLD, COLLECTOR_HOLD_DOWNLOAD_POSSIBLE)
