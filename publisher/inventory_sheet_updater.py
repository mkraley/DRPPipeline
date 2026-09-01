"""
Factory for inventory sheet updaters (data inventories vs Baserow batch import).
"""

from __future__ import annotations

from publisher.BaserowBatchSheetUpdater import BaserowBatchSheetUpdater
from publisher.GoogleSheetUpdater import GoogleSheetUpdater
from publisher.inventory_sheet_updater_base import InventorySheetUpdaterBase
from utils.Args import Args

INVENTORY_SHEET_FORMAT_DATA_INVENTORIES = "data_inventories"
INVENTORY_SHEET_FORMAT_BASEROW_BATCH = "baserow_batch"

_SUPPORTED_FORMATS = frozenset({
    INVENTORY_SHEET_FORMAT_DATA_INVENTORIES,
    INVENTORY_SHEET_FORMAT_BASEROW_BATCH,
})


def get_inventory_sheet_updater(
    sheet_format: str | None = None,
) -> InventorySheetUpdaterBase:
    """
    Return the inventory sheet updater for the configured format.

    Args:
        sheet_format: Override for ``Args.inventory_sheet_format``.

    Returns:
        ``GoogleSheetUpdater`` for ``data_inventories``, ``BaserowBatchSheetUpdater``
        for ``baserow_batch``.

    Raises:
        ValueError: When the format name is not recognized.
    """
    fmt = (
        sheet_format
        if sheet_format is not None
        else getattr(Args, "inventory_sheet_format", INVENTORY_SHEET_FORMAT_DATA_INVENTORIES)
    )
    normalized = (fmt or INVENTORY_SHEET_FORMAT_DATA_INVENTORIES).strip().lower()
    if normalized == INVENTORY_SHEET_FORMAT_DATA_INVENTORIES:
        return GoogleSheetUpdater()
    if normalized == INVENTORY_SHEET_FORMAT_BASEROW_BATCH:
        return BaserowBatchSheetUpdater()
    raise ValueError(
        f"Unsupported inventory_sheet_format {fmt!r}. "
        f"Supported values: {sorted(_SUPPORTED_FORMATS)}"
    )
