"""
Download catalog files that collection deferred for a large or xlarge project.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from collectors.BudgetedDownload import _is_complete
from collectors.UsfsAria2Export import (
    Aria2Entry,
    download_failure_message,
    format_windows_command,
    max_connections_for_url,
)
from storage import Storage
from storage.ProjectFileStore import ProjectFileRow, ProjectFileStore
from upload.UploadIssueReporter import UploadIssueReporter
from upload.UploadLargeFiles import (
    DISK_SPACE_BUFFER_BYTES,
    ensure_disk_space_for_download,
    run_aria2_downloads,
)
from utils.Args import Args
from utils.Errors import ProjectAbort
from utils.Logger import Logger
from utils.file_utils import format_file_size
from utils.inventory_status import STATUS_DOWNLOADED, STATUS_RESIZED, STATUS_UPLOADED_LARGE
from utils.project_utils import get_field
from utils.url_utils import BROWSER_HEADERS

_ACCEPTED = frozenset({STATUS_UPLOADED_LARGE, STATUS_RESIZED})


class ResumeDownload:
    """
    Fetch deferred catalog files onto the project folder.

    Prerequisites: ``uploaded - large`` or ``resized``, and no errors.
    Success status: ``downloaded``.
    """

    def run(self, drpid: int) -> None:
        """
        Download every ``project_files`` row that is not yet complete.

        Args:
            drpid: Project DRPID.
        """
        Logger.info("Starting resume_download for DRPID=%s", drpid)
        project = Storage.get(drpid)
        if project is None:
            UploadIssueReporter(drpid).error(f"Project with DRPID={drpid} not found in Storage")
            return
        reporter = UploadIssueReporter(drpid)
        if not _status_ok(project, reporter):
            return
        folder = Path(get_field(project, "folder_path") or "")
        if not folder.is_dir():
            reporter.error(f"Folder path is not a directory: {folder}")
            return
        try:
            self._download_pending(drpid, project, folder, reporter)
        except ProjectAbort:
            return

    def _download_pending(
        self,
        drpid: int,
        project: dict,
        folder: Path,
        reporter: UploadIssueReporter,
    ) -> None:
        """Download pending rows and set ``downloaded`` when all are present."""
        store = ProjectFileStore.from_storage()
        pending = store.list_pending_downloads(drpid)
        status = (project.get("status") or "").strip()
        if status == STATUS_UPLOADED_LARGE and any(row.size_bytes is None for row in pending):
            reporter.error("uploaded - large still has a file with an unknown size")
            return
        known = sum(row.size_bytes or 0 for row in pending)
        ensure_disk_space_for_download(folder, known)
        log_root = Path(Args.base_output_dir) / "logs"
        for row in pending:
            if not _fetch_row(drpid, folder, row, store, reporter, log_root):
                return
        Storage.update_record(drpid, {"status": STATUS_DOWNLOADED})
        Logger.info("resume_download completed for DRPID=%s", drpid)


def _status_ok(project: dict, reporter: UploadIssueReporter) -> bool:
    """Return False after recording an error when the status is not eligible."""
    status = (project.get("status") or "").strip()
    if status in _ACCEPTED:
        return True
    reporter.error(f"Expected status in {sorted(_ACCEPTED)!r}, got {status!r}")
    return False


def _fetch_row(
    drpid: int,
    folder: Path,
    row: ProjectFileRow,
    store: ProjectFileStore,
    reporter: UploadIssueReporter,
    log_root: Path,
) -> bool:
    """Download one deferred file. Return False when the project should stop."""
    dest = folder / row.relative_path
    if _is_complete(dest, row.size_bytes):
        store.mark_downloaded(drpid, row.relative_path, dest.stat().st_size)
        return True
    if dest.is_file():
        dest.unlink()
    if row.size_bytes is None:
        _require_unknown_file_space(folder)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _ok, fail_count = run_aria2_downloads(drpid, [_aria2_line(row, dest)], log_root=log_root)
    if fail_count or not dest.is_file():
        reporter.error(download_failure_message(f"Download failed: {row.relative_path}"))
        return False
    if row.size_bytes is not None and dest.stat().st_size != row.size_bytes:
        reporter.error(
            f"Downloaded size for {row.relative_path} does not match "
            f"{format_file_size(row.size_bytes)}"
        )
        return False
    store.mark_downloaded(drpid, row.relative_path, dest.stat().st_size)
    return True


def _require_unknown_file_space(folder: Path) -> None:
    """Stop the batch when less than 50 GiB is free before an unsized file."""
    ensure_disk_space_for_download(folder, 0)
    free = shutil.disk_usage(folder).free
    if free < DISK_SPACE_BUFFER_BYTES:
        from utils.Errors import record_crash

        record_crash(
            f"Not enough disk space before an unknown-size download into {folder}: "
            f"{format_file_size(free)} free, need {format_file_size(DISK_SPACE_BUFFER_BYTES)}"
        )


def _aria2_line(row: ProjectFileRow, dest: Path) -> str:
    """Build one aria2 command for a deferred catalog file."""
    entry = Aria2Entry(
        url=row.source_url,
        out_name=dest.name,
        dir_path=dest.parent,
        max_connections=max_connections_for_url(row.source_url),
    )
    referer = "https://irma.nps.gov/" if "irma.nps.gov" in row.source_url.lower() else None
    return format_windows_command(entry, BROWSER_HEADERS["User-Agent"], referer=referer)
