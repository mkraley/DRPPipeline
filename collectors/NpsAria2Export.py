"""
Build Windows aria2c command files for IRMA Digital Files that were not downloaded.

Each command uses ``-d`` for the product subfolder so a later download lands
beside the files already collected for that Product.
"""

from __future__ import annotations

from pathlib import Path

from collectors.NpsDownloadPlan import NpsPlannedFile, planned_file_dest
from collectors.SkipNoteFiles import SkipTarget, parse_skip_note_download_targets
from collectors.UsfsAria2Export import Aria2Entry, write_aria2_entries
from utils.url_utils import BROWSER_HEADERS

IRMA_REFERER = "https://irma.nps.gov/"
# One connection: IRMA returns from the requested start through EOF, so extra
# split connections log errorCode 8 Invalid range header and then abort.
_IRMA_CONNECTIONS = 1


def write_nps_aria2_cmd(
    drpid: int,
    folder_path: Path,
    files: list[NpsPlannedFile],
    *,
    output_dir: Path | None = None,
) -> Path | None:
    """
    Write aria2 commands for planned IRMA files that are not already on disk.

    Returns the ``.cmd`` path, or None when every planned file is present.
    """
    entries = entries_for_planned_files(folder_path, files)
    return write_aria2_entries(
        drpid,
        entries,
        output_dir=output_dir,
        user_agent=BROWSER_HEADERS["User-Agent"],
        referer=IRMA_REFERER,
        comment=f"REM DRPID {drpid} — IRMA Digital Files not downloaded",
    )


def write_nps_aria2_cmd_from_notes(
    drpid: int,
    folder_path: Path,
    status_notes: str | None,
    *,
    output_dir: Path | None = None,
) -> Path | None:
    """Write aria2 commands from skip notes, using each note's product folder."""
    targets = parse_skip_note_download_targets(status_notes)
    entries = entries_for_skip_targets(folder_path, targets)
    return write_aria2_entries(
        drpid,
        entries,
        output_dir=output_dir,
        user_agent=BROWSER_HEADERS["User-Agent"],
        referer=IRMA_REFERER,
        comment=f"REM DRPID {drpid} — IRMA Digital Files not downloaded",
    )


def entries_for_planned_files(
    folder_path: Path,
    files: list[NpsPlannedFile],
) -> list[Aria2Entry]:
    """Build aria2 entries for planned files missing under their product folder."""
    entries: list[Aria2Entry] = []
    for entry in files:
        dest = planned_file_dest(folder_path, entry.relative_dir, entry.filename)
        if dest.is_file():
            continue
        entries.append(_entry(entry.url, entry.filename, dest.parent))
    return entries


def entries_for_skip_targets(
    folder_path: Path,
    targets: list[SkipTarget],
) -> list[Aria2Entry]:
    """Build aria2 entries from skip-note targets, skipping files already on disk."""
    entries: list[Aria2Entry] = []
    for filename, url, _size, relative_dir in targets:
        dest = planned_file_dest(folder_path, relative_dir, filename)
        if dest.is_file():
            continue
        entries.append(_entry(url, filename, dest.parent))
    return entries


def _entry(url: str, filename: str, dest_dir: Path) -> Aria2Entry:
    """One IRMA aria2 entry aimed at ``dest_dir``."""
    return Aria2Entry(
        url=url,
        out_name=filename,
        dir_path=dest_dir.resolve(),
        max_connections=_IRMA_CONNECTIONS,
    )
