"""Worksheet title and range helpers for a copied inventory spreadsheet."""

from __future__ import annotations

import re
from typing import Any, Callable


def spreadsheet_title(tab_name: str) -> str:
    """
    Return the file title for a new source spreadsheet.

    Args:
        tab_name: Uppercase source initials, such as ``NRC``.

    Returns:
        ``{tab_name} Batch Import``.
    """
    return f"{tab_name} Batch Import"


def find_data_tab(tabs: list[dict[str, Any]], tab_name: str) -> dict[str, Any]:
    """
    Find the template worksheet that should be renamed.

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


def make_copy_url(template_id: str) -> str:
    """
    Return the Google Sheets link that copies a file into the signed-in account.

    Args:
        template_id: Spreadsheet id to copy.

    Returns:
        A ``/copy`` URL opened in the account that should own the new file.
    """
    return f"https://docs.google.com/spreadsheets/d/{template_id}/copy"


def spreadsheet_id_from_text(text: str) -> str:
    """
    Return a spreadsheet id from a pasted URL or bare id.

    Args:
        text: User input.

    Returns:
        Spreadsheet id.

    Raises:
        ValueError: If ``text`` is not a Sheets URL or id.
    """
    raw = text.strip()
    if "/d/" in raw:
        from utils.sheet_url_utils import parse_spreadsheet_url

        sheet_id, _gid = parse_spreadsheet_url(raw)
        return sheet_id
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", raw):
        return raw
    raise ValueError("Paste a Google Sheets URL or spreadsheet id.")


def prompt_for_copied_spreadsheet(
    template_id: str,
    editor_email: str,
    reader: Callable[[str], str] | None = None,
) -> str:
    """
    Ask for a spreadsheet the user copied into their own Drive.

    Service accounts have no Drive storage, so ``files.copy`` fails with
    ``storageQuotaExceeded`` even when the human account has free space.

    Args:
        template_id: Spreadsheet to copy.
        editor_email: Service account that must be an editor of the copy.
        reader: Prompt function. Defaults to ``input``.

    Returns:
        Spreadsheet id of the user's copy.
    """
    ask = reader or input
    print("The Drive API copy runs as the service account, which has no Drive storage.")
    print("Your Google account quota is not the one that failed.")
    print("1. Open this link while signed in to the account that should own the sheet:")
    print(f"   {make_copy_url(template_id)}")
    print("2. Make a copy.")
    if editor_email:
        print(f"3. Share that copy with {editor_email} as Editor.")
    else:
        print("3. Share that copy with the service account in google_credentials as Editor.")
    print("4. Paste the new spreadsheet URL.")
    return spreadsheet_id_from_text(ask("Spreadsheet URL: "))


def clear_values_range(tab_name: str) -> str:
    """
    Return the A1 range of data rows under a header row.

    Args:
        tab_name: Worksheet title.

    Returns:
        A quoted sheet range starting at row 2.
    """
    escaped = tab_name.replace("'", "''")
    return f"'{escaped}'!2:1000000"
