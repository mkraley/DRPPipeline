"""
Backfill status_notes external URLs for external-archive rows from adc_metadata.json.

Reads Figshare metadata saved during collection and writes the same
``External data URL: ...`` note used by AdcCollector.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sourcing.AdcFileInventory import AdcFileInventory

STATUS = "collected - external archive"
_METADATA_NAME = "adc_metadata.json"


def needs_backfill(status_notes: str | None) -> bool:
    """Return True when status_notes lacks an external URL note."""
    if not status_notes or not str(status_notes).strip():
        return True
    text = str(status_notes).strip()
    return not text.startswith("External data URL")


def resolve_metadata_path(folder_path: str | None, drpid: int, base_dir: Path) -> Path | None:
    """Locate adc_metadata.json for a DRPID."""
    candidates: list[Path] = []
    if folder_path:
        candidates.append(Path(folder_path) / _METADATA_NAME)
    candidates.append(base_dir / f"DRP{drpid:06d}" / _METADATA_NAME)
    for path in candidates:
        if path.is_file():
            return path
    return None


def backfill(
    db_path: Path,
    base_output_dir: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """
    Backfill status_notes from on-disk metadata.

    Returns:
        Tuple of (updated, skipped_no_metadata, skipped_already_has_note).
    """
    inventory = AdcFileInventory()
    connection = sqlite3.connect(db_path)
    rows = connection.execute(
        """
        SELECT DRPID, folder_path, status_notes, title
        FROM projects
        WHERE status = ?
        ORDER BY DRPID
        """,
        (STATUS,),
    ).fetchall()

    updated = 0
    skipped_no_metadata = 0
    skipped_has_note = 0

    for drpid, folder_path, status_notes, title in rows:
        if not needs_backfill(status_notes):
            skipped_has_note += 1
            continue

        meta_path = resolve_metadata_path(folder_path, drpid, base_output_dir)
        if meta_path is None:
            print(f"  DRPID {drpid}: no {_METADATA_NAME} found")
            skipped_no_metadata += 1
            continue

        article = json.loads(meta_path.read_text(encoding="utf-8"))
        note = inventory.external_archive_status_note(article)
        if not note:
            print(f"  DRPID {drpid}: metadata has no external URL ({title or ''})")
            skipped_no_metadata += 1
            continue

        print(f"  DRPID {drpid}: {note[:100]}...")
        if not dry_run:
            connection.execute(
                "UPDATE projects SET status_notes = ? WHERE DRPID = ?",
                (note, drpid),
            )
            updated += 1

    if not dry_run:
        connection.commit()
    connection.close()
    return updated, skipped_no_metadata, skipped_has_note


def main() -> None:
    """Run backfill from CLI."""
    dry_run = "--dry-run" in sys.argv
    repo = Path(__file__).resolve().parents[1]
    db_path = repo / "adc.db"
    base_dir = Path(r"C:\DataRescue\ADCData")

    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            db_path = Path(arg.split("=", 1)[1])
        if arg.startswith("--base="):
            base_dir = Path(arg.split("=", 1)[1])

    print(f"Database: {db_path}")
    print(f"Base output: {base_dir}")
    print(f"Mode: {'dry-run' if dry_run else 'update'}")
    print()

    updated, skipped_meta, skipped_note = backfill(
        db_path,
        base_dir,
        dry_run=dry_run,
    )
    print()
    print(f"Updated: {updated}")
    print(f"Skipped (already had note): {skipped_note}")
    print(f"Skipped (no metadata/URL): {skipped_meta}")


if __name__ == "__main__":
    main()
