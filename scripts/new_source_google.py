"""Add a header-only inventory tab on the shared spreadsheet."""

from __future__ import annotations

from typing import Any

from scripts.new_source_sheet import (
    assert_tab_available,
    find_data_tab,
    header_values_range,
)


def sheet_tabs(sheets: Any, spreadsheet_id: str) -> list[dict[str, Any]]:
    """
    Return worksheet properties for a spreadsheet.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.

    Returns:
        A list of ``{title, sheetId}`` dicts.
    """
    from utils.google_sheets_service import execute_sheets_request

    meta = execute_sheets_request(
        sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(title,sheetId))",
        ),
        operation_label="Sheets get spreadsheet",
    )
    return [
        {
            "title": (sheet.get("properties") or {}).get("title"),
            "sheetId": (sheet.get("properties") or {}).get("sheetId"),
        }
        for sheet in meta.get("sheets") or []
    ]


def read_header_row(sheets: Any, spreadsheet_id: str, tab_name: str) -> list[str]:
    """
    Read the first row of a worksheet.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.
        tab_name: Worksheet title.

    Returns:
        Header cell values.

    Raises:
        ValueError: If row 1 is empty.
    """
    from utils.google_sheets_service import execute_sheets_request

    result = execute_sheets_request(
        sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=header_values_range(tab_name),
        ),
        operation_label="Sheets read header row",
    )
    values = result.get("values") or []
    header = values[0] if values else []
    if not header:
        raise ValueError(f"Template tab '{tab_name}' has no header row.")
    return [str(cell) for cell in header]


def add_sheet(sheets: Any, spreadsheet_id: str, tab_name: str) -> int | None:
    """
    Add an empty worksheet.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.
        tab_name: Worksheet title.

    Returns:
        The new numeric sheet id, or None when the reply omits it.
    """
    from utils.google_sheets_service import execute_sheets_request

    result = execute_sheets_request(
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
        ),
        operation_label="Sheets add worksheet",
    )
    replies = result.get("replies") or []
    if not replies:
        return None
    properties = (replies[0].get("addSheet") or {}).get("properties") or {}
    sheet_id = properties.get("sheetId")
    if sheet_id is None:
        return None
    return int(sheet_id)


def write_header_row(
    sheets: Any,
    spreadsheet_id: str,
    tab_name: str,
    header: list[str],
) -> None:
    """
    Write a header row into row 1.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.
        tab_name: Worksheet title.
        header: Cell values for row 1.
    """
    from utils.google_sheets_service import execute_sheets_request

    execute_sheets_request(
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=header_values_range(tab_name),
            valueInputOption="RAW",
            body={"values": [header]},
        ),
        operation_label="Sheets write header row",
    )


def spreadsheet_edit_url(spreadsheet_id: str, sheet_id: int | None) -> str:
    """
    Return a URL that opens a spreadsheet, and a tab when its id is known.

    Args:
        spreadsheet_id: Spreadsheet id.
        sheet_id: Numeric worksheet id, or None.

    Returns:
        An edit URL.
    """
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    if sheet_id is None:
        return url
    return f"{url}#gid={sheet_id}"


def add_inventory_tab(
    sheets: Any,
    spreadsheet_id: str,
    template_tab: str,
    new_tab: str,
) -> str:
    """
    Add a worksheet whose first row copies the template headers.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Shared inventory spreadsheet.
        template_tab: Worksheet that already has the header row.
        new_tab: Worksheet title to create.

    Returns:
        URL that opens the new tab.

    Raises:
        RuntimeError: If adding the tab or writing headers fails.
            The message includes the spreadsheet id.
    """
    tabs = sheet_tabs(sheets, spreadsheet_id)
    assert_tab_available(tabs, new_tab)
    find_data_tab(tabs, template_tab)
    header = read_header_row(sheets, spreadsheet_id, template_tab)
    try:
        sheet_id = add_sheet(sheets, spreadsheet_id, new_tab)
        write_header_row(sheets, spreadsheet_id, new_tab, header)
    except Exception as exc:
        raise RuntimeError(f"{exc} (spreadsheet id: {spreadsheet_id})") from exc
    return spreadsheet_edit_url(spreadsheet_id, sheet_id)
