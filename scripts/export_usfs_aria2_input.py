"""
Export Windows aria2c command lines for USFS publication downloads missing on disk.

Fetches catalog pages for the given DRPIDs and writes ``.cmd`` batch files with
one complete ``aria2c`` command per large file (default: catalog size >= 1 GB
and not yet present in the project folder).

Run from repo root:
    python scripts/export_usfs_aria2_input.py --drpids 9,17,19,20
    python scripts/export_usfs_aria2_input.py --db-path usfs.db

Then download (run the whole batch, or copy one line at a time):
    aria2_inputs\\DRP000017.cmd
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsAria2Export import (  # noqa: E402
    Aria2Entry,
    DEFAULT_ARIA2_OUTPUT_DIR,
    MAX_DOWNLOAD_BYTES,
    entries_for_publication_files,
    format_windows_command,
    format_windows_commands,
    max_connections_for_url,
    write_drpid_aria2_cmd,
)
from collectors.UsfsMetadataExtractor import parse_data_access_links  # noqa: E402
from collectors.UsfsCollector import STATUS_COLLECTED_LARGE_FILE  # noqa: E402
from utils.file_utils import format_file_size, sanitize_filename  # noqa: E402
from utils.url_utils import BROWSER_HEADERS, fetch_page_body  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_OUTPUT_DIR = DEFAULT_ARIA2_OUTPUT_DIR
SKIP_NOTE_MARKER = "Skipped download (>1GB)"


def resolve_output_folder(
    drpid: int,
    folder_path: str | None,
    base_output_dir: Path,
) -> Path:
    if folder_path:
        return Path(folder_path)
    return base_output_dir / f"DRP{drpid:06d}"


def load_base_output_dir(config_path: Path) -> Path:
    if config_path.is_file():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        raw = data.get("base_output_dir")
        if raw:
            return Path(raw)
    return Path(r"C:\Documents\DataRescue\USFSData")


def load_db_path(config_path: Path) -> Path:
    if not config_path.is_file():
        return DEFAULT_DB_PATH
    raw = json.loads(config_path.read_text(encoding="utf-8")).get("db_path")
    if not raw:
        return DEFAULT_DB_PATH
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def ensure_drpid_aria2_cmd(
    conn: sqlite3.Connection,
    drpid: int,
    *,
    output_dir: Path,
    base_output_dir: Path,
    user_agent: str,
    min_bytes: int,
    missing_only: bool,
) -> tuple[Path | None, int]:
    """
    Return ``(cmd_path, line_count)`` for a DRPID, exporting ``.cmd`` when missing or empty.
    """
    from collectors.UsfsAria2Export import parse_aria2c_lines_from_cmd_file

    cmd_path = output_dir / f"DRP{drpid:06d}.cmd"
    if cmd_path.is_file():
        lines = parse_aria2c_lines_from_cmd_file(cmd_path)
        if lines:
            return cmd_path, len(lines)

    print(f"DRP {drpid}: no aria2 batch file — exporting from catalog...", file=sys.stderr)
    combined: List[Aria2Entry] = []
    count = export_drpid(
        conn,
        drpid,
        output_dir,
        base_output_dir,
        user_agent,
        min_bytes=min_bytes,
        missing_only=missing_only,
        combined_entries=combined,
    )
    if count == 0:
        return (cmd_path if cmd_path.is_file() else None), 0
    return cmd_path, count


def export_drpid(
    conn: sqlite3.Connection,
    drpid: int,
    output_dir: Path,
    base_output_dir: Path,
    user_agent: str,
    *,
    min_bytes: int,
    missing_only: bool,
    combined_entries: List[Aria2Entry],
) -> int:
    row = conn.execute(
        "SELECT DRPID, source_url, folder_path FROM projects WHERE DRPID = ?",
        (drpid,),
    ).fetchone()
    if not row:
        print(f"DRPID {drpid}: not found in database", file=sys.stderr)
        return 0

    source_url = row["source_url"]
    if not source_url:
        print(f"DRPID {drpid}: missing source_url", file=sys.stderr)
        return 0

    status, body, _, _ = fetch_page_body(source_url)
    if status != 200 or not body:
        print(f"DRPID {drpid}: failed to fetch catalog (status={status})", file=sys.stderr)
        return 0

    links = parse_data_access_links(body, source_url)
    folder = resolve_output_folder(drpid, row["folder_path"], base_output_dir)
    folder.mkdir(parents=True, exist_ok=True)

    entries = entries_for_publication_files(
        links.get("publication_files", []),
        folder,
        min_bytes=min_bytes,
        missing_only=missing_only,
    )
    if not entries:
        print(f"DRPID {drpid}: nothing to export (folder {folder})", file=sys.stderr)
        return 0

    combined_entries.extend(entries)
    out_path = write_drpid_aria2_cmd(
        drpid,
        folder,
        links.get("publication_files", []),
        output_dir=output_dir,
        min_bytes=min_bytes,
        missing_only=missing_only,
        user_agent=user_agent,
    )
    assert out_path is not None

    export_bytes = sum(
        sz
        for name, _url, sz in links.get("publication_files", [])
        if sz is not None
        and sz >= min_bytes
        and not (missing_only and (folder / sanitize_filename(name)).is_file())
    )
    print(
        f"DRPID {drpid}: wrote {len(entries)} item(s) to {out_path} "
        f"({format_file_size(export_bytes)} to download)",
        file=sys.stderr,
    )
    for entry in entries:
        print(f"  - {entry.out_name}", file=sys.stderr)
    return len(entries)


def select_drpids(conn: sqlite3.Connection, drpids_arg: str, auto_skip_notes: bool) -> List[int]:
    if drpids_arg.strip():
        return [int(x.strip()) for x in drpids_arg.split(",") if x.strip()]
    if auto_skip_notes:
        rows = conn.execute(
            """
            SELECT DRPID FROM projects
            WHERE status = ?
               OR status_notes LIKE ?
            ORDER BY DRPID
            """,
            (STATUS_COLLECTED_LARGE_FILE, f"%{SKIP_NOTE_MARKER}%"),
        ).fetchall()
        return [row["DRPID"] for row in rows]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Windows aria2c commands for missing large USFS publication downloads"
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite database (default: {DEFAULT_DB_PATH.name})",
    )
    parser.add_argument(
        "--drpids",
        type=str,
        default="",
        help="Comma-separated DRPIDs (default: rows with skipped >1GB in status_notes)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for .cmd files (default: {DEFAULT_OUTPUT_DIR.name}/)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="config.json for base_output_dir when folder_path is empty",
    )
    parser.add_argument(
        "--min-gb",
        type=float,
        default=1.0,
        help="Minimum catalog-listed size in GB to include (default: 1.0)",
    )
    parser.add_argument(
        "--include-on-disk",
        action="store_true",
        help="Include large files even if already present in the folder",
    )
    parser.add_argument(
        "--combined",
        action="store_true",
        help="Also write usfs_large_downloads.cmd with all DRPIDs combined",
    )
    parser.add_argument(
        "--no-auto-drpids",
        action="store_true",
        help="Require --drpids instead of auto-selecting from status_notes",
    )
    args = parser.parse_args()

    min_bytes = int(args.min_gb * 1024**3)
    missing_only = not args.include_on_disk

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    drpids = select_drpids(conn, args.drpids, auto_skip_notes=not args.no_auto_drpids)
    if not drpids:
        conn.close()
        parser.error("No DRPIDs to export; pass --drpids or ensure status_notes contain skip lines")

    base_output_dir = load_base_output_dir(args.config)
    user_agent = BROWSER_HEADERS["User-Agent"]
    combined: List[Aria2Entry] = []
    total_items = 0

    for drpid in drpids:
        total_items += export_drpid(
            conn,
            drpid,
            args.output_dir,
            base_output_dir,
            user_agent,
            min_bytes=min_bytes,
            missing_only=missing_only,
            combined_entries=combined,
        )

    conn.close()

    if args.combined and combined:
        combined_path = args.output_dir / "usfs_large_downloads.cmd"
        combined_path.write_text(
            format_windows_commands(combined, user_agent),
            encoding="utf-8",
        )
        print(f"Combined: {combined_path} ({len(combined)} item(s))", file=sys.stderr)

    if total_items:
        example = args.output_dir / f"DRP{drpids[0]:06d}.cmd"
        print("\nRun all downloads for one DRPID:", file=sys.stderr)
        print(f"  {example}", file=sys.stderr)
        print("Or open the .cmd file and copy individual aria2c lines.", file=sys.stderr)
    else:
        print("No download command files written.", file=sys.stderr)


if __name__ == "__main__":
    main()
