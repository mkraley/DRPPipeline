"""
Helpers for matching inventory spreadsheet column headers by prefix.

Sheets often use long header text (for example ``Download Location (where is…``).
Callers pass a short prefix such as ``Download Location`` and match the first
column whose header starts with that text (case-insensitive).
"""

from __future__ import annotations


def normalize_sheet_header(text: object) -> str:
    """Return a normalized header string for comparison."""
    return str(text or "").strip().lower()


def find_column_by_prefix(fieldnames: list[str], prefix: str) -> str | None:
    """
    Return the first column name whose header starts with ``prefix``.

    Args:
        fieldnames: CSV or sheet header names.
        prefix: Header prefix to match (case-insensitive).

    Returns:
        Matching column name, or None when no column matches.
    """
    needle = normalize_sheet_header(prefix)
    if not needle:
        return None
    for name in fieldnames:
        if normalize_sheet_header(name).startswith(needle):
            return name
    return None


def row_value_by_column_prefix(row: dict[str, str], prefix: str) -> str:
    """
    Return the cell value for the column whose header starts with ``prefix``.

    Args:
        row: One spreadsheet row as a header→value dict.
        prefix: Header prefix to match (case-insensitive).

    Returns:
        Stripped cell text, or ``""`` when no matching column or value is empty.
    """
    needle = normalize_sheet_header(prefix)
    if not needle:
        return ""
    for key, val in row.items():
        if normalize_sheet_header(key).startswith(needle):
            return (val or "").strip()
    return ""


def require_column_by_prefix(fieldnames: list[str], prefix: str) -> str:
    """
    Resolve a required column by prefix or raise ValueError.

    Args:
        fieldnames: CSV or sheet header names.
        prefix: Header prefix to match (case-insensitive).

    Returns:
        Matching column name.

    Raises:
        ValueError: When no column header starts with ``prefix``.
    """
    found = find_column_by_prefix(fieldnames, prefix)
    if found is None:
        raise ValueError(
            f"CSV missing required column starting with '{prefix}'. "
            f"Available columns: {fieldnames}"
        )
    return found
