"""
Read a preview of downloaded tables for metadata inference.

Supports CSV, TSV, TXT, JSON, XLSX (stdlib), and XLS when xlrd is installed.
Only the header row and selected value columns are kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from interactive_collector.table_preview_readers import row_groups_in_zip, rows_for_path

_MAX_DATA_ROWS = 20000
_MAX_FILE_BYTES = 30_000_000
_TABLE_SUFFIXES = {".csv", ".tsv", ".txt", ".json", ".xlsx", ".xls"}
_SKIP_NAME_PARTS = ("dictionary", "readme")


@dataclass
class TablePreview:
    """Header row plus values for columns the caller asked to keep."""

    headers: list[str]
    columns: dict[int, list[str]] = field(default_factory=dict)
    truncated: bool = False
    categories: dict[str, list[str]] = field(default_factory=dict)


def iter_folder_tables(
    folder: Path | None,
    keep_column: Callable[[str], bool],
) -> tuple[list[TablePreview], list[str]]:
    """
    Read data tables under ``folder``.

    Args:
        folder: Project output directory. Missing folders yield nothing.
        keep_column: True when that header's values should be stored.

    Returns:
        Previews, and notes about files that could not be read.
    """
    if folder is None or not folder.is_dir():
        return [], []
    previews: list[TablePreview] = []
    notes: list[str] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or _skip_file(path):
            continue
        if path.suffix.lower() == ".zip":
            previews.extend(_previews_in_zip(path, keep_column, notes))
            continue
        preview = read_table(path, keep_column)
        if preview is None and path.suffix.lower() in {".xls", ".xlsx"}:
            notes.append(f"Could not read {path.name}")
        elif preview is not None:
            previews.append(preview)
    return previews, notes


def read_table(path: Path, keep_column: Callable[[str], bool]) -> TablePreview | None:
    """Return a preview of one file, or None when it is not a readable table."""
    suffix = path.suffix.lower()
    if suffix not in _TABLE_SUFFIXES or path.stat().st_size > _MAX_FILE_BYTES:
        return None
    rows = rows_for_path(path)
    if rows is None:
        return None
    return _preview_from_rows(rows, keep_column)


def _skip_name(name: str) -> bool:
    """True for data dictionaries and readmes."""
    lowered = name.lower()
    return any(part in lowered for part in _SKIP_NAME_PARTS)


def _skip_file(path: Path) -> bool:
    """True for data dictionaries, readmes, and oversized files."""
    if _skip_name(path.name):
        return True
    try:
        return path.stat().st_size > _MAX_FILE_BYTES
    except OSError:
        return True


def _previews_in_zip(
    path: Path,
    keep_column: Callable[[str], bool],
    notes: list[str],
) -> list[TablePreview]:
    """Preview table members stored inside a zip."""
    groups, zip_notes = row_groups_in_zip(path)
    notes.extend(zip_notes)
    previews: list[TablePreview] = []
    for rows in groups:
        preview = _preview_from_rows(rows, keep_column)
        if preview is not None:
            previews.append(preview)
    return previews


def _preview_from_rows(
    rows: Iterator[list[str]],
    keep_column: Callable[[str], bool],
) -> TablePreview | None:
    """Keep the header and values for columns ``keep_column`` accepts."""
    headers: list[str] | None = None
    columns: dict[int, list[str]] = {}
    category_values: dict[int, list[str] | None] = {}
    count = 0
    truncated = False
    for row in rows:
        if headers is None:
            if not any(cell.strip() for cell in row):
                continue
            headers = [cell.strip() for cell in row]
            continue
        count += 1
        if count > _MAX_DATA_ROWS:
            truncated = True
            break
        _append_kept_values(headers, row, keep_column, columns)
        _note_categories(row, category_values)
    if not headers:
        return None
    return TablePreview(
        headers=headers,
        columns=columns,
        truncated=truncated,
        categories=_finished_categories(headers, category_values, truncated),
    )


def _append_kept_values(
    headers: list[str],
    row: list[str],
    keep_column: Callable[[str], bool],
    columns: dict[int, list[str]],
) -> None:
    """Store one data row's values for headers the caller wants."""
    for index, header in enumerate(headers):
        if index >= len(row) or not keep_column(header):
            continue
        columns.setdefault(index, []).append(row[index].strip())


_MAX_CATEGORY_VALUES = 8
_CATEGORY_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9][A-Za-z0-9 /&()'.,-]{0,38}$")


def _note_categories(row: list[str], category_values: dict[int, list[str] | None]) -> None:
    """Remember short repeated labels, and drop a column once it is free text."""
    for index, cell in enumerate(row):
        if category_values.get(index) is None and index in category_values:
            continue
        text = cell.strip()
        if not text:
            continue
        if not _CATEGORY_VALUE.match(text) or len(text.split()) > 4:
            category_values[index] = None
            continue
        bucket = category_values.setdefault(index, [])
        if bucket is None:
            continue
        if text.lower() not in {item.lower() for item in bucket}:
            bucket.append(text)
        if len(bucket) > _MAX_CATEGORY_VALUES:
            category_values[index] = None


def _finished_categories(
    headers: list[str],
    category_values: dict[int, list[str] | None],
    truncated: bool,
) -> dict[str, list[str]]:
    """Return columns whose values are a short set of labels."""
    if truncated:
        return {}
    found: dict[str, list[str]] = {}
    for index, values in category_values.items():
        if not values or len(values) < 2 or index >= len(headers):
            continue
        header = headers[index].strip()
        if header:
            found[header] = values
    return found
