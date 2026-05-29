"""
Refresh USFS inventory fields from catalog HTML without re-downloading.

Updates num_files, file_size, extensions, and status_notes from catalog-listed
sizes and existing files on disk. Does not wipe output folders or download.

Run from repo root:
    python scripts/refresh_usfs_inventory.py --drpids 9,17,19,20
    python scripts/refresh_usfs_inventory.py --db-path usfs.db
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsCollector import (  # noqa: E402
    TOTAL_SIZE_WARN_BYTES,
    UsfsCollector,
    _PDF_NAMES,
)
from collectors.UsfsMetadataExtractor import parse_data_access_links  # noqa: E402
from utils.file_utils import format_file_size  # noqa: E402
from utils.url_utils import fetch_page_body  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"


def refresh_row(
    collector: UsfsCollector,
    conn: sqlite3.Connection,
    drpid: int,
    source_url: str,
    folder_path: Path | None,
) -> None:
    status, body, _, _ = fetch_page_body(source_url)
    if status != 200 or not body:
        print(f"DRPID {drpid}: failed to fetch catalog ({status})", file=sys.stderr)
        return

    links = parse_data_access_links(body, source_url)
    publication_files = links.get("publication_files", [])
    inventory_folder = (
        folder_path
        if folder_path and folder_path.is_dir()
        else Path(f"__usfs_refresh_missing_{drpid}__")
    )
    if inventory_folder != folder_path:
        print(f"DRPID {drpid}: folder_path missing; catalog sizes only", file=sys.stderr)

    status_notes, inventory_bytes, inventory_exts = collector._process_publication_files(
        drpid,
        None,  # type: ignore[arg-type]
        inventory_folder,
        publication_files,
        download=False,
    )

    pdf_bytes = (
        collector._pdf_folder_bytes(folder_path)
        if folder_path and folder_path.is_dir()
        else 0
    )
    total_bytes = inventory_bytes + pdf_bytes
    all_exts = sorted(inventory_exts | {"pdf"})
    num_files = len(publication_files) + len(_PDF_NAMES)

    notes_parts = list(status_notes)
    if total_bytes > TOTAL_SIZE_WARN_BYTES:
        notes_parts.insert(
            0,
            f"TOTAL SIZE EXCEEDS 50 GB: {format_file_size(total_bytes)} "
            f"({num_files} files including items not downloaded; manual download may be required).",
        )

    fields = {
        "num_files": num_files,
        "file_size": format_file_size(total_bytes),
        "extensions": ", ".join(all_exts),
        "status_notes": "\n".join(notes_parts) if notes_parts else None,
    }
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE projects SET {set_clause} WHERE DRPID = ?",
        (*fields.values(), drpid),
    )
    print(
        f"DRPID {drpid}: {num_files} files, {fields['file_size']}",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh USFS num_files/file_size/status_notes from catalog (no downloads)"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH.name})",
    )
    parser.add_argument(
        "--drpids",
        type=str,
        default="",
        help="Comma-separated DRPIDs to refresh (default: all with source_url and folder_path)",
    )
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    collector = UsfsCollector()

    if args.drpids.strip():
        drpids = [int(x.strip()) for x in args.drpids.split(",") if x.strip()]
        placeholders = ",".join("?" * len(drpids))
        query = (
            f"SELECT DRPID, source_url, folder_path FROM projects "
            f"WHERE DRPID IN ({placeholders}) ORDER BY DRPID"
        )
        rows = conn.execute(query, drpids).fetchall()
    else:
        rows = conn.execute(
            "SELECT DRPID, source_url, folder_path FROM projects "
            "WHERE source_url IS NOT NULL AND source_url != '' "
            "ORDER BY DRPID"
        ).fetchall()

    for row in rows:
        folder = Path(row["folder_path"]) if row["folder_path"] else None
        refresh_row(collector, conn, row["DRPID"], row["source_url"], folder)

    conn.commit()
    conn.close()
    print(f"Done ({len(rows)} row(s))", file=sys.stderr)


if __name__ == "__main__":
    main()
