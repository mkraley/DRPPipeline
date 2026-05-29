"""
Export aria2 input files for USFS publication downloads missing on disk.

Fetches catalog pages for the given DRPIDs and writes ``.aria2.txt`` files with
``url``, ``out``, and ``dir`` lines (default: files larger than 1 GB not yet
present in the project folder).

Run from repo root:
    python scripts/export_usfs_aria2_input.py --drpids 9,17,19,20
    python scripts/export_usfs_aria2_input.py --db-path usfs.db

Then download (example):
    aria2c -c -j 1 --file-allocation=none --max-tries=0 --retry-wait=10 ^
      --user-agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36" ^
      -i aria2_inputs\\DRP000017.aria2.txt
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.UsfsCollector import MAX_DOWNLOAD_BYTES, PublicationFile  # noqa: E402
from collectors.UsfsMetadataExtractor import parse_data_access_links  # noqa: E402
from utils.file_utils import format_file_size, sanitize_filename  # noqa: E402
from utils.url_utils import BROWSER_HEADERS, fetch_page_body  # noqa: E402

DEFAULT_DB_PATH = REPO_ROOT / "usfs.db"
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "aria2_inputs"
SKIP_NOTE_MARKER = "Skipped download (>1GB)"


@dataclass(frozen=True)
class Aria2Entry:
    """One aria2 input-file item."""

    url: str
    out_name: str
    dir_path: Path
    max_connections: int


def max_connections_for_url(url: str) -> int:
    """Box shared links tolerate more connections than USDA product URLs."""
    host = (urlparse(url).hostname or "").lower()
    if "box.com" in host:
        return 16
    if host.endswith("fs.usda.gov"):
        return 4
    return 8


def entries_for_publication_files(
    publication_files: Sequence[PublicationFile],
    folder_path: Path,
    *,
    min_bytes: int = MAX_DOWNLOAD_BYTES,
    missing_only: bool = True,
) -> List[Aria2Entry]:
    """
    Build aria2 entries for publication files at or above ``min_bytes``.

    Skips files already on disk when ``missing_only`` is True.
    """
    entries: List[Aria2Entry] = []
    for filename, file_url, catalog_bytes in publication_files:
        if catalog_bytes is None or catalog_bytes < min_bytes:
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


def format_aria2_input(entries: Iterable[Aria2Entry]) -> str:
    """Format entries as an aria2 input file (UTF-8 text)."""
    blocks: List[str] = []
    for entry in entries:
        blocks.append(
            "\n".join(
                [
                    entry.url,
                    f"  out={entry.out_name}",
                    f"  dir={entry.dir_path}",
                    f"  max-connection-per-server={entry.max_connections}",
                    f"  split={entry.max_connections}",
                ]
            )
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


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


def suggested_aria2_command(input_path: Path, user_agent: str) -> str:
    """Single-line aria2c invocation for PowerShell/cmd."""
    ua = user_agent.replace('"', '\\"')
    return (
        f'aria2c -c -j 1 --file-allocation=none --max-tries=0 --retry-wait=10 '
        f'--user-agent="{ua}" -i "{input_path}"'
    )


def export_drpid(
    conn: sqlite3.Connection,
    drpid: int,
    output_dir: Path,
    base_output_dir: Path,
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
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"DRP{drpid:06d}.aria2.txt"
    out_path.write_text(format_aria2_input(entries), encoding="utf-8")

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
            "SELECT DRPID FROM projects WHERE status_notes LIKE ? ORDER BY DRPID",
            (f"%{SKIP_NOTE_MARKER}%",),
        ).fetchall()
        return [row["DRPID"] for row in rows]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export aria2 input files for missing large USFS publication downloads"
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
        help=f"Directory for .aria2.txt files (default: {DEFAULT_OUTPUT_DIR.name}/)",
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
        help="Also write usfs_large_downloads.aria2.txt with all DRPIDs combined",
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
    combined: List[Aria2Entry] = []
    total_items = 0

    for drpid in drpids:
        total_items += export_drpid(
            conn,
            drpid,
            args.output_dir,
            base_output_dir,
            min_bytes=min_bytes,
            missing_only=missing_only,
            combined_entries=combined,
        )

    conn.close()

    if args.combined and combined:
        combined_path = args.output_dir / "usfs_large_downloads.aria2.txt"
        combined_path.write_text(format_aria2_input(combined), encoding="utf-8")
        print(f"Combined: {combined_path} ({len(combined)} item(s))", file=sys.stderr)

    if total_items:
        ua = BROWSER_HEADERS["User-Agent"]
        example = args.output_dir / f"DRP{drpids[0]:06d}.aria2.txt"
        print("\nExample download command:", file=sys.stderr)
        print(suggested_aria2_command(example, ua), file=sys.stderr)
    else:
        print("No aria2 input files written.", file=sys.stderr)


if __name__ == "__main__":
    main()
