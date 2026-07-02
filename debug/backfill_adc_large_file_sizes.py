"""Backfill file_size and num_files for ADC large-file projects (read-only parse + update)."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

from utils.file_utils import format_file_size, parse_file_size_to_bytes

SKIPPED_SIZE_RE = re.compile(
    r"Skipped download \(>1GB\): .+? \(([^)]+)\)",
    re.IGNORECASE,
)
STATUSES = (
    "collected - large file",
    "uploaded - large file",
    "uploaded - expanded",
)


def skipped_bytes_from_notes(status_notes: str | None) -> tuple[int, int]:
    """
    Parse skipped large-file sizes from ADC status_notes.

    Args:
        status_notes: Project status_notes text.

    Returns:
        Tuple of (total skipped bytes, number of skipped files).
    """
    if not status_notes:
        return 0, 0
    sizes = SKIPPED_SIZE_RE.findall(status_notes)
    total = 0
    for size_text in sizes:
        parsed = parse_file_size_to_bytes(size_text.strip())
        if parsed is not None:
            total += parsed
    return total, len(sizes)


def backfill_row(
    drpid: int,
    file_size: str | None,
    num_files: int | None,
    status_notes: str | None,
) -> tuple[str, int] | None:
    """
    Compute corrected file_size and num_files when skipped sizes are missing.

    Returns:
        ``(new_file_size, new_num_files)`` or None when no change is needed.
    """
    skipped_bytes, skipped_count = skipped_bytes_from_notes(status_notes)
    if skipped_count == 0:
        return None

    current_bytes = parse_file_size_to_bytes(file_size) or 0
    current_files = int(num_files or 0)
    corrected_bytes = current_bytes + skipped_bytes
    corrected_files = current_files + skipped_count

    if corrected_bytes == current_bytes and corrected_files == current_files:
        return None
    return format_file_size(corrected_bytes), corrected_files


def main() -> None:
    """Update adc.db rows whose file_size omits skipped >1GB inventory files."""
    dry_run = "--dry-run" in sys.argv
    db_path = Path(__file__).resolve().parent.parent / "adc.db"
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        f"""
        SELECT drpid, file_size, num_files, status_notes, status
        FROM projects
        WHERE status IN ({",".join("?" * len(STATUSES))})
          AND status_notes LIKE '%Skipped download (>1GB)%'
        ORDER BY drpid
        """,
        STATUSES,
    ).fetchall()

    updated = 0
    for drpid, file_size, num_files, status_notes, status in rows:
        correction = backfill_row(drpid, file_size, num_files, status_notes)
        if correction is None:
            continue
        new_size, new_files = correction
        print(
            f"DRPID {drpid} ({status}): "
            f"num_files {num_files} -> {new_files}, "
            f"file_size {file_size!r} -> {new_size!r}"
        )
        if not dry_run:
            conn.execute(
                "UPDATE projects SET file_size = ?, num_files = ? WHERE drpid = ?",
                (new_size, new_files, drpid),
            )
        updated += 1

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"\n{'Would update' if dry_run else 'Updated'} {updated} project(s).")


if __name__ == "__main__":
    main()
