"""
Download NPS IRMA Digital Files with the shared 1 GB collector budget.
"""

from __future__ import annotations

from pathlib import Path

from collectors.NpsDownloadPlan import NpsPlannedFile, planned_file_dest
from collectors.NpsHtmlDownloadCheck import unexpected_html_message, response_meta
from utils.Args import Args
from utils.Errors import record_error, record_warning
from utils.Logger import Logger
from utils.collector_status import (
    MAX_DOWNLOAD_BYTES,
    deferred_download_skip_note,
    download_budget_exhausted,
    large_file_skip_note,
    pending_download_summary_note,
    would_exceed_download_budget,
)
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
        notes: list[str] = []
        skipped_large = False
        downloaded_bytes, _exts = folder_inventory(folder_path)
        for index, entry in enumerate(files):
            dest = planned_file_dest(folder_path, entry.relative_dir, entry.filename)
            if dest.is_file():
                continue
            expected = entry.size_bytes
            if would_exceed_download_budget(downloaded_bytes, expected):
                notes.extend(_defer_notes(files[index:]))
                skipped_large = True
                break
            if expected is not None and expected > MAX_DOWNLOAD_BYTES:
                skipped_large = True
                notes.append(large_file_skip_note(entry.filename, entry.url, expected))
                continue
            if not self._download_one(drpid, dest, entry):
                continue
            downloaded_bytes += dest.stat().st_size
            if download_budget_exhausted(downloaded_bytes) and files[index + 1 :]:
                notes.extend(_defer_notes(files[index + 1 :]))
                skipped_large = True
                break
        notes.extend(_pending_summary_notes(folder_path, files, skipped_large))
        total_bytes, extensions = folder_inventory(folder_path)
        return notes, skipped_large, total_bytes, extensions

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
            record_warning(drpid, html_note)
            return False
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


def projected_folder_bytes(folder_path: Path, files: list[NpsPlannedFile]) -> int:
    """
    Return on-disk bytes plus catalog sizes for planned files not on disk.

    A file already present anywhere under ``folder_path`` counts once, at its
    downloaded size. Missing files add ``size_bytes`` when IRMA reported one.
    """
    on_disk, _extensions = folder_inventory(folder_path)
    present = {
        path.name.casefold()
        for path in folder_path.rglob("*")
        if path.is_file()
    } if folder_path.is_dir() else set()
    pending = sum(
        int(entry.size_bytes or 0)
        for entry in files
        if entry.filename.casefold() not in present
    )
    return on_disk + pending


def count_files(folder_path: Path) -> int:
    """Return the recursive regular-file count under a project folder."""
    if not folder_path.is_dir():
        return 0
    return sum(1 for path in folder_path.rglob("*") if path.is_file())


def _defer_notes(files: list[NpsPlannedFile]) -> list[str]:
    """Build skip notes for files not downloaded because of the 1 GB budget."""
    return [
        deferred_download_skip_note(entry.filename, entry.url, entry.size_bytes)
        for entry in files
    ]


def _pending_summary_notes(
    folder_path: Path,
    files: list[NpsPlannedFile],
    skipped_large: bool,
) -> list[str]:
    """Return a pending-download summary when the 1 GB budget stopped the batch."""
    if not skipped_large:
        return []
    pending = [
        entry
        for entry in files
        if not planned_file_dest(
            folder_path, entry.relative_dir, entry.filename
        ).is_file()
    ]
    if not pending:
        return []
    return [
        pending_download_summary_note(
            len(pending),
            sum(entry.size_bytes or 0 for entry in pending),
            has_unknown_sizes=any(entry.size_bytes is None for entry in pending),
        )
    ]
