"""
Download SSA catalog files with the shared 1 GB collector budget.
"""

from __future__ import annotations

from pathlib import Path

from collectors.SsaCompleteMetadata import COMPLETE_METADATA_HEADING_SELECTOR
from collectors.SsaMetadataExtractor import SsaDownloadFile, filename_from_url
from collectors.UsfsPageDownloader import UsfsPageDownloader
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
from utils.file_utils import format_file_size, sanitize_filename

CATALOG_PDF_NAME = "catalog_page.pdf"


def destination_filename(entry: SsaDownloadFile) -> str:
    """
    Build a stable on-disk name for a catalog file.

    Uses the download URL basename (e.g. ``names.zip``), not the catalog
    resource label (often ``Resource 2``).

    Args:
        entry: Parsed download entry.

    Returns:
        Sanitized filename from the URL path.
    """
    name = entry.filename or filename_from_url(entry.url)
    return sanitize_filename(name)


def catalog_file_extensions(files: list[SsaDownloadFile]) -> set[str]:
    """Return extensions for catalog-listed download files plus the catalog PDF."""
    extensions = {"pdf"}
    for entry in files:
        suffix = Path(destination_filename(entry)).suffix
        if suffix:
            extensions.add(suffix.lstrip(".").lower())
    return extensions


class SsaFileDownloader:
    """Download SSA files via Playwright, skipping work that exceeds 1 GB."""

    def download_files(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[SsaDownloadFile],
        size_cache: dict[str, int | None],
    ) -> tuple[list[str], bool, int, set[str]]:
        """
        Download catalog files until the cumulative 1 GB budget is reached.

        Args:
            drpid: Project DRPID.
            page_downloader: Playwright helper.
            folder_path: Project output folder.
            files: Catalog file entries.
            size_cache: Mutable URL-to-size map.

        Returns:
            Status notes, large-skip flag, inventory bytes, and extensions.
        """
        notes: list[str] = []
        skipped_large = False
        downloaded_bytes = self._on_disk_bytes(folder_path, files)
        inventory_exts = catalog_file_extensions(files)

        for index, entry in enumerate(files):
            filename = destination_filename(entry)
            dest = folder_path / filename
            if dest.exists():
                Logger.info("Skipping already-downloaded: %s", filename)
                continue
            expected_bytes = self.expected_bytes(page_downloader, entry, size_cache)
            if would_exceed_download_budget(downloaded_bytes, expected_bytes):
                notes.extend(self._defer_notes(page_downloader, files[index:], size_cache))
                skipped_large = True
                break
            if expected_bytes is not None and expected_bytes > MAX_DOWNLOAD_BYTES:
                skipped_large = True
                notes.append(large_file_skip_note(filename, entry.url, expected_bytes))
                continue
            self._log_download(filename, expected_bytes)
            _written, success = page_downloader.download_file(entry.url, dest)
            if not success or not dest.is_file():
                record_error(drpid, f"Download failed: {filename} - {entry.url}")
                notes.append(f"Download failed: {filename} - {entry.url}")
                continue
            Logger.info("Downloaded: %s", filename)
            downloaded_bytes += dest.stat().st_size
            if download_budget_exhausted(downloaded_bytes) and files[index + 1 :]:
                notes.extend(self._defer_notes(page_downloader, files[index + 1 :], size_cache))
                skipped_large = True
                break

        summary = self._pending_summary(page_downloader, folder_path, files, size_cache)
        if summary:
            notes.append(summary)
        inventory_bytes = self.inventory_bytes(page_downloader, folder_path, files, size_cache)
        return notes, skipped_large, inventory_bytes, inventory_exts

    def expected_bytes(
        self,
        page_downloader: UsfsPageDownloader,
        entry: SsaDownloadFile,
        size_cache: dict[str, int | None],
    ) -> int | None:
        """Return catalog or probed Content-Length for a file."""
        if entry.url in size_cache:
            return size_cache[entry.url]
        result = entry.size_bytes
        if result is None:
            probed = page_downloader.fetch_content_length(entry.url)
            result = probed if isinstance(probed, int) and probed >= 0 else None
        size_cache[entry.url] = result
        return result

    def inventory_bytes(
        self,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[SsaDownloadFile],
        size_cache: dict[str, int | None],
    ) -> int:
        """Estimate total project bytes including files not yet on disk."""
        total_bytes = 0
        catalog_pdf = folder_path / CATALOG_PDF_NAME
        if catalog_pdf.is_file():
            total_bytes += catalog_pdf.stat().st_size
        known_names = {CATALOG_PDF_NAME}
        for entry in files:
            dest = folder_path / destination_filename(entry)
            known_names.add(dest.name)
            if dest.is_file():
                total_bytes += dest.stat().st_size
                continue
            expected = self.expected_bytes(page_downloader, entry, size_cache)
            if expected is not None:
                total_bytes += expected
        total_bytes += _extra_on_disk_bytes(folder_path, known_names)
        return total_bytes

    def write_aria2_cmd(
        self,
        drpid: int,
        folder_path: Path,
        files: list[SsaDownloadFile],
        size_cache: dict[str, int | None],
    ) -> None:
        """Export aria2 commands for catalog files still missing on disk."""
        from collectors.UsfsAria2Export import write_drpid_aria2_cmd

        pending = [
            (
                destination_filename(entry),
                entry.url,
                size_cache.get(entry.url, entry.size_bytes),
            )
            for entry in files
            if not (folder_path / destination_filename(entry)).is_file()
        ]
        cmd_path = write_drpid_aria2_cmd(drpid, folder_path, pending, min_bytes=0)
        if cmd_path:
            Logger.info("Wrote aria2 download commands for DRPID %s: %s", drpid, cmd_path)

    def _log_download(self, filename: str, expected_bytes: int | None) -> None:
        """Log a download start line."""
        if expected_bytes is not None:
            Logger.info("Downloading file: %s (%s)", filename, format_file_size(expected_bytes))
            return
        Logger.info("Downloading file: %s", filename)

    def _on_disk_bytes(self, folder_path: Path, files: list[SsaDownloadFile]) -> int:
        """Return bytes already present for catalog-listed files."""
        total_bytes = 0
        for entry in files:
            dest = folder_path / destination_filename(entry)
            if dest.is_file():
                total_bytes += dest.stat().st_size
        return total_bytes

    def _defer_notes(
        self,
        page_downloader: UsfsPageDownloader,
        entries: list[SsaDownloadFile],
        size_cache: dict[str, int | None],
    ) -> list[str]:
        """Build skip notes for files not downloaded due to size limits."""
        notes: list[str] = []
        for entry in entries:
            filename = destination_filename(entry)
            expected = self.expected_bytes(page_downloader, entry, size_cache)
            notes.append(deferred_download_skip_note(filename, entry.url, expected))
        return notes

    def _pending_summary(
        self,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[SsaDownloadFile],
        size_cache: dict[str, int | None],
    ) -> str:
        """Build a status_notes summary for catalog files still missing on disk."""
        pending = [
            entry
            for entry in files
            if not (folder_path / destination_filename(entry)).is_file()
        ]
        if not pending:
            return ""
        pending_bytes = 0
        has_unknown = False
        for entry in pending:
            expected = self.expected_bytes(page_downloader, entry, size_cache)
            if expected is None:
                has_unknown = True
            else:
                pending_bytes += expected
        return pending_download_summary_note(
            len(pending),
            pending_bytes,
            has_unknown_sizes=has_unknown,
        )

    def save_catalog_pdf(
        self,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        source_url: str,
    ) -> bool:
        """Render the catalog page to PDF with Complete Metadata expanded."""
        dest = folder_path / CATALOG_PDF_NAME
        return page_downloader.url_to_pdf(
            source_url,
            dest,
            open_details_selector=COMPLETE_METADATA_HEADING_SELECTOR,
        )

    def save_html_resource_pdfs(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        resources: list[SsaDownloadFile],
    ) -> list[str]:
        """Print HTML landing pages to PDFs named from each page title."""
        notes: list[str] = []
        for entry in resources:
            fallback = Path(filename_from_url(entry.url)).stem or "page"
            dest = page_downloader.url_to_titled_pdf(
                entry.url,
                folder_path,
                fallback_stem=fallback,
            )
            if dest is None:
                record_warning(drpid, f"Failed to save HTML resource PDF: {entry.url}")
                notes.append(f"Failed to save HTML resource PDF: {entry.url}")
                continue
            Logger.info("Saved HTML resource PDF: %s", dest.name)
        return notes


def _extra_on_disk_bytes(folder_path: Path, known_names: set[str]) -> int:
    """Sum sizes of files in ``folder_path`` not already counted."""
    total_bytes = 0
    if not folder_path.is_dir():
        return total_bytes
    for path in folder_path.iterdir():
        if path.is_file() and path.name not in known_names:
            total_bytes += path.stat().st_size
    return total_bytes
