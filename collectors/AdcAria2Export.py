"""
Build Windows aria2c command files for large ADC publication downloads.

Used by AdcCollector when files are skipped (>1 GB).
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from collectors.UsfsAria2Export import (
    Aria2Entry,
    format_windows_commands,
    max_connections_for_url,
)
from sourcing.AdcFileInventory import MAX_DOWNLOAD_BYTES
from utils.file_utils import sanitize_filename
from utils.url_utils import BROWSER_HEADERS

InventoryFile = tuple[str, str, int | None]
DEFAULT_ARIA2_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "aria2_inputs"


def entries_for_inventory_files(
    files: Sequence[InventoryFile],
    folder_path: Path,
    *,
    min_bytes: int = MAX_DOWNLOAD_BYTES,
    missing_only: bool = True,
) -> list[Aria2Entry]:
    """
    Build aria2 entries for inventory files at or above ``min_bytes``.

    Args:
        files: Sequence of ``(filename, url, size_bytes)`` tuples.
        folder_path: Destination directory for downloads.
        min_bytes: Minimum file size to include.
        missing_only: Skip files already present on disk.

    Returns:
        List of aria2 download entries.
    """
    entries: list[Aria2Entry] = []
    for filename, file_url, size_bytes in files:
        if size_bytes is None or size_bytes < min_bytes:
            continue
        out_name = sanitize_filename(filename)
        dest = folder_path / out_name
        if missing_only and dest.is_file():
            continue
        entries.append(
            Aria2Entry(
                url=file_url,
                out_name=out_name,
                dir_path=folder_path.resolve(),
                max_connections=max_connections_for_url(file_url),
            )
        )
    return entries


def write_drpid_aria2_cmd(
    drpid: int,
    folder_path: Path,
    files: Sequence[InventoryFile],
    *,
    output_dir: Path | None = None,
    min_bytes: int = MAX_DOWNLOAD_BYTES,
    missing_only: bool = True,
    user_agent: str | None = None,
) -> Path | None:
    """
    Write ``DRP######.cmd`` for missing large ADC files.

    Returns:
        Path written, or None when there was nothing to export.
    """
    entries = entries_for_inventory_files(
        files,
        folder_path,
        min_bytes=min_bytes,
        missing_only=missing_only,
    )
    if not entries:
        return None

    out_dir = output_dir or DEFAULT_ARIA2_OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"DRP{drpid:06d}.cmd"
    ua = user_agent or BROWSER_HEADERS["User-Agent"]
    out_path.write_text(format_windows_commands(entries, ua, drpid=drpid), encoding="utf-8")
    return out_path
