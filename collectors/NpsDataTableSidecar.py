"""
Write Data Table Info CSV sidecars next to NPS Data Package files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from collectors.NpsDownloadPlan import NpsPlannedFile, sidecar_filename
from sourcing.NpsCatalogClient import NpsCatalogClient
from utils.Errors import record_warning
from utils.Logger import Logger

FOLDER_TABLE_INFO_NAME = "data_table_info.csv"
_SIDECAR_COLUMNS = ("column_name", "definition", "storage", "unit", "scales")
_FOLDER_COLUMNS = ("source_file",) + _SIDECAR_COLUMNS


def write_data_table_csv(dest: Path, rows: list[dict[str, Any]]) -> None:
    """
    Write LoadDataTable rows as a UTF-8-sig CSV sidecar.

    Args:
        dest: Output CSV path.
        rows: IRMA LoadDataTable objects.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_SIDECAR_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(_sidecar_cells(row))


def write_folder_data_table_csv(dest: Path, rows: list[dict[str, str]]) -> None:
    """Write combined Data Table Info for one project or product folder."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FOLDER_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in _FOLDER_COLUMNS})


def write_sidecars_for_files(
    drpid: int,
    folder_path: Path,
    files: list[NpsPlannedFile],
    client: NpsCatalogClient,
) -> list[str]:
    """
    Fetch and write Data Table Info CSVs for holdings that have table metadata.

    Args:
        drpid: Project DRPID for warnings.
        folder_path: Project output folder.
        files: Planned downloads (sidecars use the same relative dirs).
        client: IRMA catalog client.

    Returns:
        Status notes for failed sidecar fetches.
    """
    notes: list[str] = []
    combined: dict[str, list[dict[str, str]]] = {}
    for entry in files:
        if entry.data_table_count <= 0 or entry.resource_id is None:
            continue
        if entry.reference_id is None:
            continue
        dest = folder_path / entry.relative_dir / sidecar_filename(entry.filename)
        try:
            rows = client.fetch_data_table(entry.reference_id, entry.resource_id)
        except RuntimeError as exc:
            message = f"Data Table Info failed for {entry.filename}: {exc}"
            record_warning(drpid, message)
            notes.append(message)
            continue
        if not rows:
            continue
        write_data_table_csv(dest, rows)
        folder_rows = combined.setdefault(entry.relative_dir, [])
        for row in rows:
            folder_rows.append({"source_file": entry.filename, **_sidecar_cells(row)})
        Logger.info("Wrote Data Table Info sidecar: %s", dest.name)
    for relative_dir, folder_rows in combined.items():
        dest = folder_path / relative_dir / FOLDER_TABLE_INFO_NAME
        write_folder_data_table_csv(dest, folder_rows)
        Logger.info("Wrote Data Table Info file: %s", dest)
    return notes


def _sidecar_cells(row: dict[str, Any]) -> dict[str, str]:
    """Map one LoadDataTable object onto sidecar CSV columns."""
    return {
        "column_name": str(row.get("ColumnName") or ""),
        "definition": str(row.get("Definition") or ""),
        "storage": str(row.get("Storage") or ""),
        "unit": str(row.get("Unit") or ""),
        "scales": _format_scales(row.get("DataTableScales")),
    }


def _format_scales(raw: Any) -> str:
    """Serialize optional coded-value scales for a CSV cell."""
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return json.dumps(raw, ensure_ascii=True)
    except (TypeError, ValueError):
        return str(raw)
