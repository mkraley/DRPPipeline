"""
Zip files still waiting to upload, one or more archives per project.

Reads ``Skipped download (>1GB)`` notes. Without ``--max-size``, one stored
zip holds the deferred files. With ``--max-size``, ``<drpid>a.zip`` holds
every project folder and catalog file, and later letters hold the deferred
content files packed up to that size. A zip file already larger than that
limit is left as-is and listed in ``<drpid>-not-zipped.txt``. Paths inside
each new zip are
``product-folder/file``, ready for DataLumos Import From Zip.

From the repo root::

    python scripts/zip_deferred_uploads.py 429 439 677 812
    python scripts/zip_deferred_uploads.py 429 --max-size 20GB
    python scripts/zip_deferred_uploads.py 429 --max-size 20GB --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.SkipNoteFiles import parse_skip_note_download_targets  # noqa: E402
from scripts.DeferredZipParts import (  # noqa: E402
    part_suffix,
    plan_zip_parts,
    write_stored_zip,
)
from scripts.export_usfs_aria2_input import (  # noqa: E402
    load_base_output_dir,
    load_db_path,
    load_google_sheet_name,
    resolve_output_folder,
)
from utils.file_utils import format_file_size, output_folder_name, parse_file_size_to_bytes  # noqa: E402

DEFAULT_CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_DRPIDS = (429, 439, 677, 812)


def group_skip_files(status_notes: str | None) -> dict[str, list[str]]:
    """Group skip-note filenames by product folder, in note order."""
    grouped: dict[str, list[str]] = {}
    for name, _url, _size, folder in parse_skip_note_download_targets(status_notes):
        names = grouped.setdefault(folder, [])
        if name not in names:
            names.append(name)
    return grouped


def resolve_product_dir(project_folder: Path, folder_name: str) -> Path:
    """Return the on-disk product directory named in a skip note."""
    if not folder_name:
        return project_folder
    direct = project_folder / folder_name
    if direct.is_dir():
        return direct
    matches = [
        path
        for path in project_folder.iterdir()
        if path.is_dir() and path.name.startswith(folder_name)
    ]
    if len(matches) == 1:
        return matches[0]
    raise FileNotFoundError(f"Product folder not found: {folder_name}")


def collect_folder_files(
    project_folder: Path,
    folder_name: str,
    names: list[str],
) -> list[Path]:
    """Return on-disk paths for one folder, stopping when any file is missing."""
    product_dir = resolve_product_dir(project_folder, folder_name)
    paths: list[Path] = []
    missing: list[Path] = []
    for name in names:
        path = product_dir / name
        if path.is_file():
            paths.append(path)
        else:
            missing.append(path)
    if missing:
        listed = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing file(s) for {folder_name or '(root)'}: {listed}")
    return paths


def collect_project_files(project_folder: Path, grouped: dict[str, list[str]]) -> list[Path]:
    """Return every deferred file for the project, in skip-note order."""
    paths: list[Path] = []
    for folder_name, names in grouped.items():
        paths.extend(collect_folder_files(project_folder, folder_name, names))
    return paths


def zip_output_path(
    output_root: Path,
    drpid: int,
    *,
    prefix: str,
    part_index: int | None = None,
) -> Path:
    """Return one archive path. Letter suffixes are ``<drpid>a.zip`` and so on."""
    if part_index is None:
        return output_root / f"{output_folder_name(drpid, prefix=prefix)}.zip"
    return output_root / f"{drpid}{part_suffix(part_index)}.zip"


def load_project_row(db_path: Path, drpid: int) -> tuple[str | None, str | None]:
    """Return ``(status_notes, folder_path)`` for one project."""
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT status_notes, folder_path FROM projects WHERE DRPID = ?",
            (drpid,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise LookupError(f"DRPID {drpid} not found")
    return row[0], row[1]


def zip_project(
    drpid: int,
    *,
    db_path: Path,
    base_output_dir: Path,
    output_root: Path,
    sheet_name: str,
    dry_run: bool,
    max_bytes: int | None = None,
) -> int:
    """Write the project's zip parts. Return the total byte count."""
    notes, folder_path = load_project_row(db_path, drpid)
    project_folder = resolve_output_folder(
        drpid,
        folder_path,
        base_output_dir,
        sheet_name=sheet_name,
    )
    deferred = collect_project_files(project_folder, group_skip_files(notes))
    parts, omitted = plan_zip_parts(project_folder, deferred, max_bytes)
    _note_omitted(drpid, output_root, omitted, dry_run=dry_run)
    return _write_parts(
        drpid,
        project_folder,
        parts,
        output_root=output_root,
        sheet_name=sheet_name,
        dry_run=dry_run,
        max_bytes=max_bytes,
    )


def _write_parts(
    drpid: int,
    project_folder: Path,
    parts: list[tuple[list[str], list[Path]]],
    *,
    output_root: Path,
    sheet_name: str,
    dry_run: bool,
    max_bytes: int | None,
) -> int:
    """Print and optionally write each planned zip. Return the total byte count."""
    total_bytes = 0
    for index, (directories, files) in enumerate(parts):
        part_index = None if max_bytes is None else index
        dest = zip_output_path(output_root, drpid, prefix=sheet_name, part_index=part_index)
        part_bytes = sum(path.stat().st_size for path in files)
        total_bytes += part_bytes
        _report_part(drpid, dest, directories, files, part_bytes, max_bytes)
        if not dry_run and (files or directories):
            write_stored_zip(project_folder, files, dest, directories)
    return total_bytes


def _note_omitted(drpid: int, output_root: Path, omitted: list[Path], *, dry_run: bool) -> None:
    """Print and, unless this is a dry run, save zip files left out of the new archives."""
    if not omitted:
        return
    print(f"DRPID {drpid} not included in a new zip ({len(omitted)} file(s)):")
    for path in omitted:
        print(f"  {path.resolve()}")
    if dry_run:
        return
    note = output_root / f"{drpid}-not-zipped.txt"
    note.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(f"{path.resolve()}\n" for path in omitted)
    note.write_text(lines, encoding="utf-8-sig")
    print(f"DRPID {drpid} note: {note}")


def _report_part(
    drpid: int,
    dest: Path,
    directories: list[str],
    files: list[Path],
    part_bytes: int,
    max_bytes: int | None,
) -> None:
    """Print one zip's contents, including a file that cannot fit under the limit."""
    print(
        f"DRPID {drpid} {dest.name}: {len(directories)} folder(s), "
        f"{len(files)} file(s), {format_file_size(part_bytes)}"
    )
    if max_bytes is None:
        return
    for path in files:
        size = path.stat().st_size
        if size > max_bytes:
            print(
                f"  {path.name} is {format_file_size(size)}, "
                f"above {format_file_size(max_bytes)}, so it is alone in this zip"
            )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse DRPIDs and output options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "drpids",
        nargs="*",
        type=int,
        default=list(DEFAULT_DRPIDS),
        help="Projects to zip (default: 429 439 677 812)",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for the zip files (default: <base_output_dir>\\pending_upload_zips)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-size",
        type=_max_size_arg,
        default=None,
        help='Maximum size of each content zip, for example "20GB"',
    )
    return parser.parse_args(argv)


def _max_size_arg(value: str) -> int:
    """Parse a positive size such as ``20GB``."""
    parsed = parse_file_size_to_bytes(value)
    if parsed is None or parsed <= 0:
        raise argparse.ArgumentTypeError(f"Invalid size: {value}")
    return parsed


def main(argv: list[str] | None = None) -> int:
    """Zip deferred uploads for the requested projects."""
    args = _parse_args(argv)
    base_output_dir = load_base_output_dir(args.config)
    output_root = args.output or (base_output_dir / "pending_upload_zips")
    sheet_name = load_google_sheet_name(args.config)
    db_path = load_db_path(args.config)
    total_bytes = 0
    for drpid in args.drpids:
        total_bytes += zip_project(
            drpid,
            db_path=db_path,
            base_output_dir=base_output_dir,
            output_root=output_root,
            sheet_name=sheet_name,
            dry_run=args.dry_run,
            max_bytes=args.max_size,
        )
    print(f"Output directory: {output_root}")
    print(f"Total: {format_file_size(total_bytes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
