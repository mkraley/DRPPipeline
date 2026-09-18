"""
Download NPS IRMA Digital Files with the shared 1 GB collector budget.
"""

from __future__ import annotations

from pathlib import Path

from collectors.NpsDownloadPlan import NpsPlannedFile
from utils.Args import Args
from utils.Errors import record_error
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

_HTML_MARKERS = (b"<html", b"<!doctype html")
_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 DRPPipeline-NPS",
    "Accept": "*/*",
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

        Args:
            drpid: Project DRPID.
            folder_path: Project output folder.
            files: Planned Digital Files.

        Returns:
            Status notes, large-skip flag, on-disk bytes, and extensions.
        """
        notes: list[str] = []
        skipped_large = False
        downloaded_bytes = 0
        for index, entry in enumerate(files):
            dest = folder_path / entry.relative_dir / entry.filename
            if dest.is_file():
                downloaded_bytes += dest.stat().st_size
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
        """Download one file and reject HTML login pages."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        timeout_ms = int(getattr(Args, "download_timeout_ms", 30 * 60 * 1000) or 30 * 60 * 1000)
        Logger.info("Downloading %s (%s)", entry.filename, format_file_size(entry.size_bytes or 0))
        try:
            _written, success = download_via_url(
                entry.url,
                dest,
                headers=_DOWNLOAD_HEADERS,
                timeout_sec=max(30, timeout_ms // 1000),
                resume=True,
            )
        except Exception as exc:
            record_error(drpid, f"Download failed: {entry.filename} - {entry.url} ({exc})")
            return False
        if not success or not dest.is_file():
            record_error(drpid, f"Download failed: {entry.filename} - {entry.url}")
            return False
        if _looks_like_html(dest):
            dest.unlink(missing_ok=True)
            record_error(
                drpid,
                f"Download returned HTML (likely restricted): {entry.filename} - {entry.url}",
            )
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
        if not (folder_path / entry.relative_dir / entry.filename).is_file()
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


def _looks_like_html(path: Path) -> bool:
    """Return True when a downloaded body is an HTML login or error page."""
    try:
        size = path.stat().st_size
        head = path.read_bytes()[:800].lower()
    except OSError:
        return False
    if size > 200_000:
        return False
    return any(marker in head for marker in _HTML_MARKERS)
