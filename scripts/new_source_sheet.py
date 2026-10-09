"""Tab names and header ranges on the shared inventory spreadsheet."""

from __future__ import annotations

from typing import Any

INVENTORY_SPREADSHEET_ID = "1WwOfNtWUvMC69HCTO95Rk-KbjpVwZWJilgeihbdv_3A"
HEADER_TEMPLATE_TAB = "Baserow Batch Import Template (please download)"


def quoted_tab(tab_name: str) -> str:
    """
    Return a tab name quoted for an A1 range.

    Args:
        tab_name: Worksheet title.

    Returns:
        A single-quoted title with embedded quotes doubled.
    """
    return "'" + tab_name.replace("'", "''") + "'"


def header_values_range(tab_name: str) -> str:
    """
    Return the A1 range of the header row.

    Args:
        tab_name: Worksheet title.

    Returns:
        A quoted sheet range for row 1.
    """
    return f"{quoted_tab(tab_name)}!1:1"


def find_data_tab(tabs: list[dict[str, Any]], tab_name: str) -> dict[str, Any]:
    """
    Find the template worksheet whose header row should be copied.

    Args:
        tabs: Sheet property dicts with ``title`` and ``sheetId``.
        tab_name: Template ``google_sheet_name``.

    Returns:
        The matching tab property dict.

    Raises:
        ValueError: If the tab is missing.
    """
    exact = [tab for tab in tabs if tab.get("title") == tab_name]
    if not exact:
        folded = [
            tab
            for tab in tabs
            if str(tab.get("title") or "").casefold() == tab_name.casefold()
        ]
        exact = folded if len(folded) == 1 else []
    if len(exact) != 1:
        names = ", ".join(str(tab.get("title")) for tab in tabs) or "(none)"
        raise ValueError(f"Template tab '{tab_name}' was not found. Tabs: {names}")
    return exact[0]


def assert_tab_available(tabs: list[dict[str, Any]], tab_name: str) -> None:
    """
    Reject a worksheet title that is already in the spreadsheet.

    Args:
        tabs: Sheet property dicts with ``title``.
        tab_name: Proposed worksheet title.

    Raises:
        ValueError: If a tab with the same name already exists.
    """
    for tab in tabs:
        title = str(tab.get("title") or "")
        if title.casefold() == tab_name.casefold():
            raise ValueError(f"Tab '{tab_name}' already exists.")
