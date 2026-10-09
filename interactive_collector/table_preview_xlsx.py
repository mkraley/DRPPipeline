"""Read rows from an xlsx workbook using only the Python standard library."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET


def xlsx_rows(path: Path) -> Iterator[list[str]] | None:
    """Yield rows from the first worksheet of an xlsx file."""
    try:
        return xlsx_rows_from_bytes(path.read_bytes())
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError):
        return None


def xlsx_rows_from_bytes(data: bytes) -> Iterator[list[str]] | None:
    """Yield rows from xlsx bytes."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None
    with archive:
        strings = _shared_strings(archive)
        sheet_name = _first_sheet_name(archive)
        if not sheet_name:
            return None
        sheet_xml = archive.read(sheet_name)
    return _iter_sheet_rows(io.BytesIO(sheet_xml), strings)


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Return the workbook shared-string table, or an empty list."""
    try:
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values: list[str] = []
    for item in root:
        if _local(item.tag) != "si":
            continue
        parts = [node.text or "" for node in item.iter() if _local(node.tag) == "t"]
        values.append("".join(parts))
    return values


def _first_sheet_name(archive: zipfile.ZipFile) -> str:
    """Return the first worksheet path inside the xlsx zip."""
    names = [
        name
        for name in archive.namelist()
        if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
    ]
    return sorted(names)[0] if names else ""


def _iter_sheet_rows(handle: io.BytesIO, strings: list[str]) -> Iterator[list[str]]:
    """Yield cell values for each worksheet row."""
    cells: dict[int, str] = {}
    for _event, elem in ET.iterparse(handle, events=("end",)):
        tag = _local(elem.tag)
        if tag == "c":
            cells[_column_index(elem.get("r") or "")] = _cell_text(elem, strings)
            elem.clear()
        elif tag == "row":
            if cells:
                last = min(max(cells), 39)
                yield [cells.get(index, "") for index in range(last + 1)]
            cells = {}
            elem.clear()


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    """Return the display text of one worksheet cell."""
    kind = cell.get("t") or ""
    if kind == "inlineStr":
        parts = [node.text or "" for node in cell.iter() if _local(node.tag) == "t"]
        return "".join(parts).strip()
    value_node = next((node for node in cell if _local(node.tag) == "v"), None)
    if value_node is None or value_node.text is None:
        return ""
    raw = value_node.text.strip()
    if kind == "s":
        return _shared_string(strings, raw)
    return raw


def _shared_string(strings: list[str], raw: str) -> str:
    """Look up one shared-string index."""
    try:
        return strings[int(raw)].strip()
    except (IndexError, ValueError):
        return ""


def _column_index(cell_ref: str) -> int:
    """Convert an A1-style reference to a zero-based column index."""
    index = 0
    for char in cell_ref:
        if not char.isalpha():
            break
        index = index * 26 + (ord(char.upper()) - 64)
    return max(index - 1, 0)


def _local(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]
