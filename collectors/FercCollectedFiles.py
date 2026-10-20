"""Write FERC details, dictionary, and dataset files."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from collectors.FercDatasetClient import DATA_PAGE_SIZE, FercDatasetClient

DETAILS_NAME = "details.json"
DICTIONARY_NAME = "dictionary.csv"
DATASET_NAME = "dataset.csv"
LANDING_PDF_NAME = "landing_page.pdf"

_DICTIONARY_COLUMNS = (
    "column_id",
    "attribute",
    "mapping",
    "column_name",
    "sql_type",
    "data_type",
    "description",
    "description_url",
    "identifier_type",
    "nullable",
    "format",
    "validations",
    "validation_url",
)


def write_details_json(path: Path, payload: dict[str, Any]) -> None:
    """
    Write the details response as UTF-8 JSON.

    Args:
        path: Destination file.
        payload: Details object.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def write_dictionary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """
    Write dictionary rows as a UTF-8-sig CSV.

    Args:
        path: Destination file.
        rows: Embedded or API dictionary rows.
    """
    columns = _dictionary_columns(rows)
    _write_csv(path, columns, rows)


def write_dataset_csv(
    path: Path,
    client: FercDatasetClient,
    dataset_id: int,
    *,
    page_size: int = DATA_PAGE_SIZE,
    pause_sec: float = 0.0,
) -> int:
    """
    Page the data API and write ``dataset.csv``.

    Args:
        path: Destination file.
        client: Dataset API client.
        dataset_id: FERC dataset id.
        page_size: Rows per request.
        pause_sec: Delay between pages after the first.

    Returns:
        Number of data rows written.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    offset = 0
    columns: list[str] | None = None
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        while True:
            page = client.fetch_data_page(dataset_id, offset=offset, limit=page_size)
            rows = page["row_data"]
            columns = _ensure_columns(writer, columns, rows)
            if columns:
                for row in rows:
                    writer.writerow([_cell(row.get(column)) for column in columns])
            written += len(rows)
            if not page["has_more"] or not rows:
                break
            offset += len(rows)
            if pause_sec > 0:
                time.sleep(pause_sec)
    return written


def _ensure_columns(
    writer: Any,
    columns: list[str] | None,
    rows: list[dict[str, Any]],
) -> list[str] | None:
    """Write the header from the first non-empty page."""
    if columns is not None:
        return columns
    if not rows:
        return None
    found = list(rows[0].keys())
    writer.writerow(found)
    return found


def _dictionary_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Return preferred dictionary columns, then any extras."""
    present = {key for row in rows for key in row}
    ordered = [name for name in _DICTIONARY_COLUMNS if name in present]
    extras = sorted(present.difference(ordered))
    return ordered + extras


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    """Write ``rows`` with a header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_cell(row.get(column)) for column in columns])


def _cell(value: Any) -> Any:
    """Return a CSV cell, encoding nested JSON as text."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value
