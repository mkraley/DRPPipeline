"""
Fill FERC keywords, time range, data types, and geographic coverage.

Uses the same inference as the interactive collector Fill metadata button
for dates, data types, and geography. Keywords come from the FERC catalog
families in ``collectors/FercKeywords.py``: ICPSR subject terms when one fits,
plus the form or program name.
``dictionary.csv`` is ignored. Column names with underscores, such as
``Issuance_Date``, are treated as words. An end date later than today is
clipped to today, and start and end are both ``YYYY`` or both ``YYYY-MM-DD``.
Tables larger than 30 MB are skipped, and date or state columns are used
only when the table preview is complete (at most 20,000 data rows).

Run from the repo root:

    python scripts/infer_ferc_metadata.py
    python scripts/infer_ferc_metadata.py --dry-run
    python scripts/infer_ferc_metadata.py --ids 27,34
    python scripts/infer_ferc_metadata.py --overwrite
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.FercKeywords import apply_ferc_keywords  # noqa: E402
from interactive_collector.metadata_inference import infer_project_metadata  # noqa: E402
from utils.drpid_list import parse_drpid_ids  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "ferc.db"
METADATA_FIELDS = (
    "keywords",
    "time_start",
    "time_end",
    "data_types",
    "geographic_coverage",
)


def field_updates(
    stored: dict[str, Any],
    inferred: dict[str, str],
    *,
    overwrite: bool,
) -> dict[str, str]:
    """
    Return inferred fields that should be written.

    Empty inferred values are left alone unless ``overwrite`` is set. Overwrite
    replaces a stored value, and clears it when inference no longer supports it.
    """
    updates: dict[str, str] = {}
    for name in METADATA_FIELDS:
        incoming = (inferred.get(name) or "").strip()
        current = str(stored.get(name) or "").strip()
        if not overwrite:
            if not incoming or current:
                continue
            updates[name] = incoming
            continue
        if current != incoming:
            updates[name] = incoming
    return updates


def fill_ferc_metadata(
    db_path: Path,
    *,
    ids: list[int] | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    limit: int = 0,
) -> int:
    """
    Infer metadata for collected FERC projects and write empty fields.

    Args:
        db_path: SQLite database that holds the projects table.
        ids: When set, only these DRPIDs are considered.
        overwrite: Replace stored values, clearing a field inference leaves empty.
        dry_run: Report updates without writing them.
        limit: Stop after this many candidate rows. Zero means no limit.

    Returns:
        Number of projects that would change, or that were updated.
    """
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    updated = 0
    try:
        for row in _candidate_rows(connection, ids, limit):
            if _fill_row(connection, row, overwrite=overwrite, dry_run=dry_run):
                updated += 1
    finally:
        connection.close()
    return updated


def main() -> None:
    """Parse arguments and fill metadata on collected FERC projects."""
    parser = argparse.ArgumentParser(description="Backfill inferred FERC metadata fields")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--ids", default="", help="DRPIDs, e.g. 27,34 or 1-10")
    parser.add_argument("--limit", type=int, default=0, help="Max projects (0 = all)")
    parser.add_argument("--overwrite", action="store_true", help="Replace stored values")
    parser.add_argument("--dry-run", action="store_true", help="Print updates without writing")
    args = parser.parse_args()
    ids = parse_drpid_ids(args.ids) if args.ids.strip() else None
    updated = fill_ferc_metadata(
        args.db_path,
        ids=ids,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    print(f"Done: updated={updated} db={args.db_path}", flush=True)


def _candidate_rows(
    connection: sqlite3.Connection,
    ids: list[int] | None,
    limit: int,
) -> list[sqlite3.Row]:
    """Return projects that have an output folder."""
    columns = ", ".join(["DRPID", "title", "summary", "folder_path", *METADATA_FIELDS])
    query = (
        f"SELECT {columns} FROM projects "
        "WHERE folder_path IS NOT NULL AND TRIM(folder_path) != '' "
        "ORDER BY DRPID"
    )
    rows = list(connection.execute(query))
    if ids is not None:
        wanted = set(ids)
        rows = [row for row in rows if int(row["DRPID"]) in wanted]
    if limit > 0:
        return rows[:limit]
    return rows


def _fill_row(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    *,
    overwrite: bool,
    dry_run: bool,
) -> bool:
    """Write one project's inferred fields. Return True when something changes."""
    folder = Path(str(row["folder_path"]))
    if not folder.is_dir():
        print(f"DRPID {row['DRPID']}: folder missing ({folder})", file=sys.stderr, flush=True)
        return False
    inferred, notes = infer_project_metadata(
        str(row["title"] or ""),
        str(row["summary"] or ""),
        folder,
    )
    apply_ferc_keywords(inferred, str(row["title"] or ""), str(row["summary"] or ""))
    for note in notes:
        print(f"DRPID {row['DRPID']}: {note}", file=sys.stderr, flush=True)
    updates = field_updates(dict(row), inferred, overwrite=overwrite)
    if not updates:
        return False
    print(f"DRPID {row['DRPID']}: {updates}", flush=True)
    if dry_run:
        return True
    _write_updates(connection, int(row["DRPID"]), updates)
    return True


def _write_updates(connection: sqlite3.Connection, drpid: int, updates: dict[str, str]) -> None:
    """Persist inferred fields for one DRPID."""
    assignments = ", ".join(f"{name} = ?" for name in updates)
    connection.execute(
        f"UPDATE projects SET {assignments} WHERE DRPID = ?",
        (*[value or None for value in updates.values()], drpid),
    )
    connection.commit()


if __name__ == "__main__":
    main()
