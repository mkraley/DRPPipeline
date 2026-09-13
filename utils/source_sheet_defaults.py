"""Default inventory-sheet settings for a newly created pipeline source."""

from __future__ import annotations

from typing import Any

DEFAULT_BASEROW_CONTACT = "mike@kraley.com"
NEW_SOURCE_INVENTORY_SHEET_FORMAT = "baserow_batch"


def new_source_sheet_defaults(contact: str | None = None) -> dict[str, Any]:
    """
    Return Baserow batch-sheet keys for a new source section.

    Existing CDC/AHRQ-style sources keep the global ``data_inventories`` default
    unless they set these keys explicitly.

    Args:
        contact: Contact email for the Baserow Contact column. When empty,
            ``DEFAULT_BASEROW_CONTACT`` is used.

    Returns:
        ``inventory_sheet_format``, ``baserow_contact``, and
        ``default_metadata_available``.
    """
    email = (contact or "").strip() or DEFAULT_BASEROW_CONTACT
    return {
        "inventory_sheet_format": NEW_SOURCE_INVENTORY_SHEET_FORMAT,
        "baserow_contact": email,
        "default_metadata_available": False,
    }
