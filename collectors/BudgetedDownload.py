"""
Download catalog files until the shared 1 GiB budget is exhausted.

Source collectors supply the file list and a one-file download function.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from collectors.PlannedFile import PlannedFile, is_generated_sidecar
from storage.ProjectFileStore import ProjectFileRow, ProjectFileStore
from utils.collector_status import (
    deferred_download_skip_note,
    download_budget_exhausted,
    pending_download_summary_note,
    would_exceed_download_budget,
)
from utils.inventory_status import (
    DEFERRED_COLLECT_STATUSES,
    classify_collected_status,
)
from utils.Logger import Logger


DownloadOne = Callable[[PlannedFile, Path], bool]


@dataclass(frozen=True)
class BudgetedDownloadResult:
    """Outcome of one budgeted download pass."""

    notes: list[str]
    deferred: bool


class BudgetedDownload:
    """Apply the 1 GiB budget and record large/xlarge file rows."""

    def download_until_budget(
        self,
        drpid: int,
        folder: Path,
        files: list[PlannedFile],
        download_one: DownloadOne,
        write_sidecars: Callable[[], None] | None = None,
    ) -> BudgetedDownloadResult:
        """
        Download ``files`` until the next file would pass 1 GiB.

        Args:
            drpid: Project DRPID, used only in log messages.
            folder: Project output folder.
            files: Catalog files in collect order.
            download_one: Source-specific download. Returns False after recording
                a failure. Raises ``ProjectAbort`` for a fatal file.
            write_sidecars: Called after the download pass, including when the
                budget stopped the pass.

        Returns:
            Notes for deferred files, and whether any file was deferred.
        """
        notes, deferred = self._download_files(drpid, folder, files, download_one)
        if write_sidecars is not None:
            write_sidecars()
        return BudgetedDownloadResult(notes=notes, deferred=deferred)

    def commit_inventory(
        self,
        drpid: int,
        folder: Path,
        files: list[PlannedFile],
    ) -> str:
        """
        Classify the full inventory and store file rows for large/xlarge projects.

        Args:
            drpid: Project DRPID.
            folder: Project output folder.
            files: Every referenced data file, including ones already deferred.

        Returns:
            ``collected``, ``collected - large``, or ``collected - xlarge``.
        """
        known_bytes, has_unknown, rows = _inventory_rows(drpid, folder, files)
        status = classify_collected_status(known_bytes, has_unknown_size=has_unknown)
        store = _store_or_none()
        if store is None:
            return status
        if status in DEFERRED_COLLECT_STATUSES:
            store.replace_for_project(drpid, rows)
        else:
            store.delete_for_project(drpid)
        return status

    def _download_files(
        self,
        drpid: int,
        folder: Path,
        files: list[PlannedFile],
        download_one: DownloadOne,
    ) -> tuple[list[str], bool]:
        """Download until a file must be deferred."""
        downloaded_bytes = _budget_bytes_on_disk(folder)
        for index, planned in enumerate(files):
            dest = planned.destination(folder)
            if _is_complete(dest, planned.size_bytes):
                continue
            if dest.is_file():
                dest.unlink()
            if _must_defer(downloaded_bytes, planned.size_bytes):
                Logger.info(
                    "DRPID %s: deferring %s file(s) after the 1 GiB budget",
                    drpid,
                    len(files) - index,
                )
                return _defer_notes(files[index:]), True
            if not download_one(planned, dest):
                continue
            if dest.is_file():
                downloaded_bytes += dest.stat().st_size
            if download_budget_exhausted(downloaded_bytes) and files[index + 1 :]:
                return _defer_notes(files[index + 1 :]), True
        return [], False


def _store_or_none() -> ProjectFileStore | None:
    """Return the file store when SQLite storage is open."""
    from storage import Storage
    from storage.StorageSQLLite import StorageSQLLite

    instance = getattr(Storage, "_instance", None)
    if not isinstance(instance, StorageSQLLite):
        return None
    return ProjectFileStore(instance.sqlite_connection())


def _must_defer(downloaded_bytes: int, size_bytes: int | None) -> bool:
    """Return True when this file should not be started."""
    if size_bytes is None:
        return True
    return would_exceed_download_budget(downloaded_bytes, size_bytes)


def _is_complete(dest: Path, size_bytes: int | None) -> bool:
    """Return True when ``dest`` exists at the expected size."""
    if not dest.is_file():
        return False
    if size_bytes is None:
        return True
    return dest.stat().st_size == size_bytes


def _budget_bytes_on_disk(folder: Path) -> int:
    """Return bytes of non-sidecar files already in the project folder."""
    if not folder.is_dir():
        return 0
    total = 0
    for path in folder.rglob("*"):
        if path.is_file() and not is_generated_sidecar(path):
            total += path.stat().st_size
    return total


def _defer_notes(files: list[PlannedFile]) -> list[str]:
    """Build skip notes plus one remaining-download summary."""
    notes = [
        deferred_download_skip_note(
            item.filename(),
            item.source_url,
            item.size_bytes,
            relative_dir=item.relative_dir(),
        )
        for item in files
    ]
    summary = pending_download_summary_note(
        len(files),
        sum(item.size_bytes or 0 for item in files),
        has_unknown_sizes=any(item.size_bytes is None for item in files),
    )
    if summary:
        notes.append(summary)
    return notes


def _inventory_rows(
    drpid: int,
    folder: Path,
    files: list[PlannedFile],
) -> tuple[int, bool, list[ProjectFileRow]]:
    """Return known bytes, whether any size is unknown, and table rows."""
    known = 0
    has_unknown = False
    rows: list[ProjectFileRow] = []
    for planned in files:
        size, complete, unknown = _file_inventory(folder, planned)
        has_unknown = has_unknown or unknown
        if size is not None:
            known += size
        rows.append(
            ProjectFileRow(
                drpid=drpid,
                relative_path=planned.relative_path,
                size_bytes=size if size is not None else planned.size_bytes,
                source_url=planned.source_url,
                downloaded=complete,
                uploaded=False,
            )
        )
    return known, has_unknown, rows


def _file_inventory(
    folder: Path,
    planned: PlannedFile,
) -> tuple[int | None, bool, bool]:
    """Return size contribution, completeness, and unknown-size flag."""
    dest = planned.destination(folder)
    if planned.size_bytes is not None:
        complete = _is_complete(dest, planned.size_bytes)
        return planned.size_bytes, complete, False
    if dest.is_file():
        return dest.stat().st_size, True, False
    return None, False, True
