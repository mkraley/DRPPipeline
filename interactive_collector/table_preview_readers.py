"""Row iterators for CSV, JSON, XLS, and zip members."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Iterator

from interactive_collector.table_preview_xlsx import xlsx_rows, xlsx_rows_from_bytes

_TABLE_SUFFIXES = {".csv", ".tsv", ".txt", ".json", ".xlsx", ".xls"}
_SKIP_NAME_PARTS = ("dictionary", "readme")
_MAX_FILE_BYTES = 30_000_000


def rows_for_path(path: Path) -> Iterator[list[str]] | None:
    """Yield rows for a supported table file."""
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return xlsx_rows(path)
    if suffix == ".xls":
        return _xls_rows(path)
    if suffix == ".json":
        return _json_rows(path.read_text(encoding="utf-8-sig", errors="replace"))
    if suffix in {".csv", ".tsv", ".txt"}:
        return delimited_rows(path.read_text(encoding="utf-8-sig", errors="replace"))
    return None


def row_groups_in_zip(path: Path) -> tuple[list[Iterator[list[str]]], list[str]]:
    """Return row iterators for table members of a zip, plus read errors."""
    groups: list[Iterator[list[str]]] = []
    notes: list[str] = []
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return groups, [f"Could not read {path.name}"]
    with archive:
        for info in archive.infolist():
            rows = _zip_member_rows(archive, info)
            if rows is not None:
                groups.append(rows)
    return groups, notes


def delimited_rows(text: str) -> Iterator[list[str]] | None:
    """Yield rows when the text is comma- or tab-delimited."""
    sample = text[:4000]
    if "\t" not in sample and "," not in sample:
        return None
    delimiter = "\t" if sample.count("\t") >= sample.count(",") else ","
    return iter(csv.reader(io.StringIO(text), delimiter=delimiter))


def _json_rows(text: str) -> Iterator[list[str]] | None:
    """Yield a header row and records from a JSON list of objects."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return None
    headers = [str(key) for key in payload[0].keys()]

    def _generate() -> Iterator[list[str]]:
        yield headers
        for item in payload:
            if isinstance(item, dict):
                yield [str(item.get(header, "") or "") for header in headers]

    return _generate()


def _xls_rows(path: Path) -> Iterator[list[str]] | None:
    """Yield rows from an .xls workbook when xlrd is installed."""
    try:
        import xlrd
    except ImportError:
        return None
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)

    def _generate() -> Iterator[list[str]]:
        for row_index in range(sheet.nrows):
            yield [
                str(sheet.cell_value(row_index, col) or "").strip()
                for col in range(sheet.ncols)
            ]

    return _generate()


def _zip_member_rows(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
) -> Iterator[list[str]] | None:
    """Return rows for one zip member, or None when it is not a table."""
    if info.is_dir() or info.file_size > _MAX_FILE_BYTES:
        return None
    suffix = Path(info.filename).suffix.lower()
    if suffix not in _TABLE_SUFFIXES or _skip_name(info.filename):
        return None
    data = archive.read(info.filename)
    if suffix == ".xlsx":
        return xlsx_rows_from_bytes(data)
    if suffix == ".json":
        return _json_rows(data.decode("utf-8-sig", errors="replace"))
    if suffix in {".csv", ".tsv", ".txt"}:
        return delimited_rows(data.decode("utf-8-sig", errors="replace"))
    return None


def _skip_name(name: str) -> bool:
    """True for data dictionaries and readmes."""
    lowered = name.lower()
    return any(part in lowered for part in _SKIP_NAME_PARTS)
