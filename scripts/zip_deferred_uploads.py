"""
Zip files still waiting to upload, one archive per product folder.

Reads ``Skipped download (>1GB)`` notes and writes a stored zip for each
product folder. Paths inside the zip are ``folder/file``, ready for
DataLumos Import From Zip.

From the repo root::

    python scripts/zip_deferred_uploads.py 429 439 677 812
    python scripts/zip_deferred_uploads.py 429 --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from collectors.SkipNoteFiles import parse_skip_note_download_targets  # noqa: E402
from scripts.export_usfs_aria2_input import (  # noqa: E402
    load_base_output_dir,
    load_db_path,
    load_google_sheet_name,
    resolve_output_folder,
)
from utils.file_utils import format_file_size, output_folder_name  # noqa: E402

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


def write_stored_zip(project_folder: Path, paths: list[Path], dest: Path) -> None:
    """Write a stored zip using paths relative to the project folder."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    root = project_folder.resolve()
    partial = dest.with_suffix(dest.suffix + ".partial")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in paths:
            resolved = path.resolve()
            archive.write(resolved, resolved.relative_to(root).as_posix())
    partial.replace(dest)


def zip_output_path(output_root: Path, drpid: int, folder_name: str, *, prefix: str) -> Path:
    """Return ``output_root/<NPS######>/<folder>.zip``."""
    archive_name = f"{folder_name}.zip" if folder_name else "_root.zip"
    return output_root / output_folder_name(drpid, prefix=prefix) / archive_name


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
) -> int:
    """Write one zip per product folder. Return the total byte count."""
    notes, folder_path = load_project_row(db_path, drpid)
    project_folder = resolve_output_folder(
        drpid,
        folder_path,
        base_output_dir,
        sheet_name=sheet_name,
    )
    total_bytes = 0
    for folder_name, names in group_skip_files(notes).items():
        paths = collect_folder_files(project_folder, folder_name, names)
        dest = zip_output_path(output_root, drpid, folder_name, prefix=sheet_name)
        folder_bytes = sum(path.stat().st_size for path in paths)
        total_bytes += folder_bytes
        print(
            f"DRPID {drpid} {dest.name}: {len(paths)} file(s), {format_file_size(folder_bytes)}"
        )
        if not dry_run:
            write_stored_zip(project_folder, paths, dest)
    return total_bytes


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
    return parser.parse_args(argv)


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
        )
    print(f"Output directory: {output_root}")
    print(f"Total: {format_file_size(total_bytes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
