"""
Build NPS download destinations: product folders and public Digital Files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sourcing.NpsReferenceRules import file_resource_id, public_digital_files
from utils.file_utils import sanitize_filename

PROJECT_FILES_FOLDER = "_project_files"
SIDECAR_SUFFIX = "_data_table_info.csv"


@dataclass(frozen=True)
class NpsPlannedFile:
    """One public Digital File to download into a project or product folder."""

    url: str
    filename: str
    relative_dir: str
    size_bytes: int | None = None
    resource_id: int | None = None
    data_table_count: int = 0
    reference_id: int | None = None


def product_folder_name(product_id: int, title: str) -> str:
    """
    Build a Windows-safe product subfolder name.

    Args:
        product_id: IRMA Product id.
        title: Product title.
    """
    stem = sanitize_filename(title, max_length=80)
    return sanitize_filename(f"{product_id}_{stem}", max_length=120)


def sidecar_filename(data_filename: str) -> str:
    """Return the Data Table Info CSV name next to a data file."""
    stem = sanitize_filename(data_filename).rsplit(".", 1)[0]
    return f"{stem}{SIDECAR_SUFFIX}"


def planned_files_for_profile(
    profile: dict[str, Any],
    relative_dir: str,
    holdings: list[dict[str, Any]] | None = None,
) -> list[NpsPlannedFile]:
    """
    Map public Digital Files onto download destinations.

    Args:
        profile: IRMA Profile JSON.
        relative_dir: Subfolder under the project output folder.
        holdings: Optional GetHoldings rows for size and DataTableCount.
    """
    holdings_by_id, holdings_by_url = _index_holdings(holdings or [])
    reference_id = profile.get("referenceId")
    planned: list[NpsPlannedFile] = []
    for item in public_digital_files(profile):
        url = str(item.get("url") or "").strip()
        filename = sanitize_filename(str(item.get("fileName") or item.get("FileName") or "") or url.rsplit("/", 1)[-1])
        resource_id = file_resource_id(item)
        holding = _matching_holding(resource_id, url, holdings_by_id, holdings_by_url)
        size_bytes = _optional_int(item.get("fileSize") or item.get("FileSize"))
        table_count = 0
        if holding:
            resource_id = resource_id or _optional_int(holding.get("Id"))
            size_bytes = size_bytes or _optional_int(holding.get("FileSize"))
            table_count = int(holding.get("DataTableCount") or 0)
            url = str(holding.get("Url") or url)
            filename = sanitize_filename(str(holding.get("FileDescription") or filename))
        if not url or filename in {"Untitled", ""}:
            continue
        planned.append(
            NpsPlannedFile(
                url=url,
                filename=filename,
                relative_dir=relative_dir,
                size_bytes=size_bytes,
                resource_id=resource_id,
                data_table_count=table_count,
                reference_id=int(reference_id) if reference_id is not None else None,
            )
        )
    return planned


def _index_holdings(
    holdings: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Index holdings by id and download URL."""
    by_id: dict[int, dict[str, Any]] = {}
    by_url: dict[str, dict[str, Any]] = {}
    for row in holdings:
        holding_id = _optional_int(row.get("Id"))
        if holding_id is not None:
            by_id[holding_id] = row
        url = str(row.get("Url") or "").strip()
        if url:
            by_url[url] = row
    return by_id, by_url


def _matching_holding(
    resource_id: int | None,
    url: str,
    by_id: dict[int, dict[str, Any]],
    by_url: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Find a holdings row for a filesAndLinks item."""
    if resource_id is not None and resource_id in by_id:
        return by_id[resource_id]
    return by_url.get(url)


def _optional_int(value: Any) -> int | None:
    """Parse an optional integer, returning None when missing or invalid."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
