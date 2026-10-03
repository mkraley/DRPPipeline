"""
Download NPS IRMA Digital Files with the shared 1 GB collector budget.
"""

from __future__ import annotations

from pathlib import Path

from collectors.BudgetedDownload import BudgetedDownload
from collectors.NpsDownloadPlan import NpsPlannedFile, planned_file_dest
from collectors.NpsHtmlDownloadCheck import unexpected_html_message, response_meta
from collectors.PlannedFile import PlannedFile, relative_posix
from utils.Args import Args
from utils.Errors import abort_project, record_error
from utils.Logger import Logger
from utils.collector_status import pending_download_summary_note
from utils.download_with_progress import download_via_url
from utils.file_utils import format_file_size

_DOWNLOAD_HEADERS = {
    "Accept": "*/*",
    "Referer": "https://irma.nps.gov/",
}


class NpsFileDownloader:
    """Stream public Digital Files to disk, skipping work over 1 GB."""

    def download_files(
        self,
        drpid: int,
        folder_path: Path,
        files: list[NpsPlannedFile],
    ) -> tuple[list[str], bool, int, set[str]]:
        """
        Download planned files until the cumulative 1 GB budget is reached.

        Existing files already on disk under ``folder_path`` count toward the
        budget so sequential Product batches share one project-wide limit.

        Args:
            drpid: Project DRPID.
            folder_path: Project output folder.
            files: Planned Digital Files.

        Returns:
            Status notes, large-skip flag, on-disk bytes, and extensions.
        """
        planned = [_planned_from_nps(entry) for entry in files]
        by_path = {item.relative_path: entry for item, entry in zip(planned, files)}
        outcome = BudgetedDownload().download_until_budget(
            drpid,
            folder_path,
            planned,
            lambda item, dest: self._download_one(drpid, dest, by_path[item.relative_path]),
        )
        total_bytes, extensions = folder_inventory(folder_path)
        return outcome.notes, outcome.deferred, total_bytes, extensions

    def _download_one(self, drpid: int, dest: Path, entry: NpsPlannedFile) -> bool:
        """Download one file and reject HTML app/error pages."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        timeout_ms = int(getattr(Args, "download_timeout_ms", 30 * 60 * 1000) or 30 * 60 * 1000)
        Logger.info("Downloading %s (%s)", entry.filename, format_file_size(entry.size_bytes or 0))
        meta: dict[str, object] = {}
        try:
            _written, success = download_via_url(
                entry.url,
                dest,
                headers=_DOWNLOAD_HEADERS,
                timeout_sec=max(30, timeout_ms // 1000),
                resume=True,
                progress_interval_mb=10.0,
                on_response=lambda response: meta.update(response_meta(response)),
            )
        except Exception as exc:
            record_error(drpid, f"Download failed: {entry.filename} - {entry.url} ({exc})")
            return False
        if not success or not dest.is_file():
            record_error(drpid, f"Download failed: {entry.filename} - {entry.url}")
            return False
        html_note = unexpected_html_message(
            dest,
            filename=entry.filename,
            url=entry.url,
            status_code=int(meta["status_code"]) if meta.get("status_code") is not None else None,
            content_type=str(meta.get("content_type") or ""),
            final_url=str(meta.get("final_url") or ""),
        )
        if html_note:
            dest.unlink(missing_ok=True)
            abort_project(drpid, html_note)
        Logger.info("Downloaded: %s", entry.filename)
        return True


def folder_inventory(folder_path: Path) -> tuple[int, set[str]]:
    """Return recursive file bytes and extensions under a project folder."""
    total_bytes = 0
    extensions: set[str] = set()
    if not folder_path.is_dir():
        return total_bytes, extensions
    for path in folder_path.rglob("*"):
        if not path.is_file():
            continue
        total_bytes += path.stat().st_size
        if path.suffix:
            extensions.add(path.suffix.lstrip(".").lower())
    return total_bytes, extensions


def missing_planned_files(
    folder_path: Path,
    files: list[NpsPlannedFile],
) -> list[NpsPlannedFile]:
    """Return planned files whose product path is not already a file on disk."""
    return [
        entry
        for entry in files
        if not planned_file_dest(
            folder_path, entry.relative_dir, entry.filename
        ).is_file()
    ]


def projected_folder_bytes(folder_path: Path, files: list[NpsPlannedFile]) -> int:
    """
    Return on-disk bytes plus catalog sizes for planned files not on disk.

    A file at its planned path counts at its downloaded size. The same filename
    in another product still adds its catalog size when that path is missing.
    """
    on_disk, _extensions = folder_inventory(folder_path)
    pending = sum(
        int(entry.size_bytes or 0)
        for entry in missing_planned_files(folder_path, files)
    )
    return on_disk + pending


def count_files(folder_path: Path) -> int:
    """Return the recursive regular-file count under a project folder."""
    if not folder_path.is_dir():
        return 0
    return sum(1 for path in folder_path.rglob("*") if path.is_file())


def projected_file_count(folder_path: Path, files: list[NpsPlannedFile]) -> int:
    """Return on-disk files plus planned catalog files that are not on disk yet."""
    return count_files(folder_path) + len(missing_planned_files(folder_path, files))


def _planned_from_nps(entry: NpsPlannedFile) -> PlannedFile:
    """Map an NPS holding onto the shared planned-file record."""
    return PlannedFile(
        relative_path=relative_posix(entry.relative_dir, entry.filename),
        source_url=entry.url,
        size_bytes=entry.size_bytes,
    )


def notes_with_remaining_summary(
    notes: list[str],
    folder_path: Path,
    files: list[NpsPlannedFile],
) -> list[str]:
    """Replace any batch summary with one line covering every file still missing."""
    kept = [line for line in notes if not line.startswith("Remaining downloads:")]
    pending = missing_planned_files(folder_path, files)
    if not pending:
        return kept
    summary = pending_download_summary_note(
        len(pending),
        sum(entry.size_bytes or 0 for entry in pending),
        has_unknown_sizes=any(entry.size_bytes is None for entry in pending),
    )
    if summary:
        kept.append(summary)
    return kept


