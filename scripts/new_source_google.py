"""Copy an inventory spreadsheet and rename its data tab for a new source."""

from __future__ import annotations

from typing import Any

from scripts.new_source_sheet import clear_values_range, find_data_tab, spreadsheet_title


def rename_spreadsheet(
    sheets: Any,
    spreadsheet_id: str,
    sheet_id: int,
    tab_title: str,
    file_title: str,
) -> None:
    """
    Rename the data tab and the spreadsheet file.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.
        sheet_id: Numeric worksheet id.
        tab_title: New worksheet title.
        file_title: New spreadsheet title.
    """
    from utils.google_sheets_service import execute_sheets_request

    execute_sheets_request(
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": sheet_id, "title": tab_title},
                            "fields": "title",
                        }
                    },
                    {
                        "updateSpreadsheetProperties": {
                            "properties": {"title": file_title},
                            "fields": "title",
                        }
                    },
                ]
            },
        ),
        operation_label="Sheets rename spreadsheet",
    )


def clear_data_rows(sheets: Any, spreadsheet_id: str, tab_name: str) -> None:
    """
    Clear every cell below the header row.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.
        tab_name: Worksheet title.
    """
    from utils.google_sheets_service import execute_sheets_request

    execute_sheets_request(
        sheets.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=clear_values_range(tab_name),
            body={},
        ),
        operation_label="Sheets clear data rows",
    )


def sheet_tabs(sheets: Any, spreadsheet_id: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Return a spreadsheet title and its worksheet properties.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet id.

    Returns:
        Spreadsheet title and a list of ``{title, sheetId}`` dicts.
    """
    from utils.google_sheets_service import execute_sheets_request

    meta = execute_sheets_request(
        sheets.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="properties(title),sheets(properties(title,sheetId))",
        ),
        operation_label="Sheets get spreadsheet",
    )
    title = str((meta.get("properties") or {}).get("title") or "")
    tabs = [
        {
            "title": (sheet.get("properties") or {}).get("title"),
            "sheetId": (sheet.get("properties") or {}).get("sheetId"),
        }
        for sheet in meta.get("sheets") or []
    ]
    return title, tabs


def prepare_existing_spreadsheet(
    sheets: Any,
    spreadsheet_id: str,
    old_tab: str,
    new_tab: str,
) -> str:
    """
    Rename a user-owned copy and clear its data rows.

    Args:
        sheets: Sheets API v4 service.
        spreadsheet_id: Spreadsheet the user copied into their Drive.
        old_tab: Worksheet title on the template.
        new_tab: Worksheet title to use.

    Returns:
        URL that opens the spreadsheet.

    Raises:
        RuntimeError: If rename or clear fails. The message includes the id.
    """
    _original_title, tabs = sheet_tabs(sheets, spreadsheet_id)
    tab = find_data_tab(tabs, old_tab)
    file_title = spreadsheet_title(new_tab)
    try:
        rename_spreadsheet(sheets, spreadsheet_id, int(tab["sheetId"]), new_tab, file_title)
        clear_data_rows(sheets, spreadsheet_id, new_tab)
    except Exception as exc:
        raise RuntimeError(f"{exc} (spreadsheet id: {spreadsheet_id})") from exc
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
