"""
Bureau of Transportation Statistics (BTS) ROSA P collector for DRP Pipeline.

Harvests metadata and downloads dataset files from rosap.ntl.bts.gov detail pages.
The site blocks plain HTTP clients, so Playwright is used for page loads and downloads.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from collectors.BtsMetadataExtractor import (
    BtsDownloadFile,
    infer_data_types,
    parse_detail_page,
)
from collectors.CollectorBase import CollectorBase
from collectors.UsfsPageDownloader import UsfsPageDownloader
from utils.Args import Args
from utils.collector_status import (
    MAX_DOWNLOAD_BYTES,
    deferred_download_skip_note,
    download_budget_exhausted,
    large_file_skip_note,
    would_exceed_download_budget,
)
from utils.Errors import record_error, record_warning
from utils.IcpsrGeographicNormalizer import (
    log_geographic_normalization,
    normalize_geographic_metadata,
)
from utils.Logger import Logger
from utils.file_utils import create_output_folder, format_file_size, sanitize_filename
from utils.zip_extension_scan import (
    DEFAULT_ZIP_EXTENSION_SCAN_BUDGET,
    scan_zip_extensions_in_folder,
)

_BTS_HOST = "rosap.ntl.bts.gov"
_CATALOG_PDF_NAME = "catalog_page.pdf"
_FETCH_TIMEOUT_SEC = 120


class BtsCollector(CollectorBase):
    """Collect BTS ROSA P dataset metadata and files."""

    _storage_status_mode = "inventory"

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize the collector.

        Args:
            headless: Launch Playwright headless when True.
        """
        self._headless = headless
        self._page_downloader: UsfsPageDownloader | None = None

    def run(self, drpid: int) -> None:
        """
        Run collection for one BTS project.

        Args:
            drpid: DRPID of the project to process.
        """
        record, source_url = self.load_project(drpid)
        if record is None or source_url is None:
            return

        self._page_downloader = UsfsPageDownloader(headless=self._headless)
        try:
            result = self._collect(source_url, drpid, record)
            self.apply_result_to_storage(drpid, result)
        except Exception as exc:
            record_error(drpid, f"Exception during BTS collection for DRPID {drpid}: {exc}")
        finally:
            self._page_downloader.close()
            self._page_downloader = None

    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        page_downloader = self._page_downloader
        if page_downloader is None:
            record_error(drpid, "BTS page downloader not initialized")
            return {}

        if not self.validate_url(drpid, url):
            return {}

        if _BTS_HOST not in url or "/view/dot/" not in url:
            record_error(drpid, f"Not a BTS ROSA P view URL: {url}")
            return {}

        status, body, _content_type, _logical_404 = page_downloader.fetch_page_html(
            url,
            timeout=_FETCH_TIMEOUT_SEC,
        )
        if status != 200 or not body:
            record_error(drpid, f"Failed to fetch BTS detail page (status={status}): {url}")
            return {}

        parsed = parse_detail_page(body, url)
        if not parsed.get("title"):
            record_warning(drpid, "Title not found on BTS detail page")

        result = {key: value for key, value in parsed.items() if not key.startswith("_")}
        self._apply_geographic_coverage(drpid, result)

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if folder_path is None:
            record_error(drpid, "Failed to create output folder")
            return result

        result["folder_path"] = str(folder_path)
        self._save_catalog_pdf(drpid, page_downloader, folder_path, url)

        download_files: list[BtsDownloadFile] = parsed.get("_download_files", [])
        status_notes, skipped_large = self._download_files(
            drpid,
            page_downloader,
            folder_path,
            download_files,
        )

        extensions, total_bytes, num_files = self._folder_inventory(folder_path)
        self._enrich_extensions_from_archives(drpid, folder_path, extensions)
        if extensions:
            result["extensions"] = ", ".join(sorted(extensions))
        result["num_files"] = num_files
        result["file_size"] = format_file_size(total_bytes)
        data_types = infer_data_types(
            result.get("title", ""),
            result.get("summary", ""),
            result.get("keywords", ""),
            str(parsed.get("_format_label", "")),
            file_extensions=extensions,
        )
        if data_types:
            result["data_types"] = data_types
        result["download_date"] = date.today().isoformat()
        if status_notes:
            result["status_notes"] = "\n".join(status_notes)
        result["_skipped_large_file"] = skipped_large
        if skipped_large:
            self._write_aria2_cmd(drpid, folder_path, download_files)

        Logger.info(
            "BTS collection complete for DRPID %s: %s files, %s",
            drpid,
            num_files,
            result.get("file_size"),
        )
        return result

    def _apply_geographic_coverage(self, drpid: int, result: dict[str, Any]) -> None:
        """Normalize geographic coverage to ICPSR thesaurus terms when possible."""
        raw = str(result.get("geographic_coverage") or "").strip()
        if not raw:
            return
        geo = normalize_geographic_metadata(geographic_extent_description=raw)
        log_geographic_normalization(
            geo,
            geographic_extent_description=raw,
            context=f"DRPID {drpid}",
        )
        if geo.geographic_coverage:
            result["geographic_coverage"] = geo.geographic_coverage
        for warning in geo.warnings:
            record_warning(drpid, warning)

    def _save_catalog_pdf(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        source_url: str,
    ) -> None:
        """Render the source catalog page to PDF."""
        dest = folder_path / _CATALOG_PDF_NAME
        if not page_downloader.url_to_pdf(source_url, dest):
            record_warning(drpid, f"Failed to save catalog PDF: {_CATALOG_PDF_NAME}")

    def _download_files(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[BtsDownloadFile],
    ) -> tuple[list[str], bool]:
        """
        Download main and supporting files via Playwright.

        Stops when the cumulative download budget (1 GB) is reached and records
        remaining files in ``status_notes`` for ``upload_large_files``.

        Returns:
            Tuple of status note lines and whether any large file was skipped.
        """
        notes: list[str] = []
        skipped_large = False
        downloaded_bytes = self._downloaded_bytes_on_disk(folder_path, files)

        for index, entry in enumerate(files):
            filename = self._destination_filename(entry)
            dest = folder_path / filename
            if dest.exists():
                Logger.info("Skipping already-downloaded: %s", filename)
                continue

            if would_exceed_download_budget(downloaded_bytes, entry.size_bytes):
                notes.extend(self._defer_download_notes(files[index:]))
                skipped_large = True
                break

            catalog_bytes = entry.size_bytes
            if catalog_bytes is not None and catalog_bytes > MAX_DOWNLOAD_BYTES:
                skipped_large = True
                notes.append(large_file_skip_note(filename, entry.url, catalog_bytes))
                continue

            if entry.size_bytes is not None:
                Logger.info(
                    "Downloading %s file: %s (%s)",
                    "main" if entry.is_main else "supporting",
                    filename,
                    format_file_size(entry.size_bytes),
                )
            else:
                Logger.info(
                    "Downloading %s file: %s",
                    "main" if entry.is_main else "supporting",
                    filename,
                )
            _bytes_written, success = page_downloader.download_file(entry.url, dest)
            if not success or not dest.is_file():
                record_error(drpid, f"Download failed: {filename} - {entry.url}")
                notes.append(f"Download failed: {filename} - {entry.url}")
                continue
            Logger.info("Downloaded: %s", filename)
            downloaded_bytes += dest.stat().st_size
            if download_budget_exhausted(downloaded_bytes):
                remaining = files[index + 1 :]
                if remaining:
                    notes.extend(self._defer_download_notes(remaining))
                    skipped_large = True
                break

        return notes, skipped_large

    def _downloaded_bytes_on_disk(
        self,
        folder_path: Path,
        files: list[BtsDownloadFile],
    ) -> int:
        """Return total bytes already present for catalog-listed download files."""
        total_bytes = 0
        for entry in files:
            dest = folder_path / self._destination_filename(entry)
            if dest.is_file():
                total_bytes += dest.stat().st_size
        return total_bytes

    def _defer_download_notes(self, entries: list[BtsDownloadFile]) -> list[str]:
        """Build status_notes lines for files not downloaded due to size limits."""
        notes: list[str] = []
        for entry in entries:
            filename = self._destination_filename(entry)
            notes.append(
                deferred_download_skip_note(filename, entry.url, entry.size_bytes)
            )
        return notes

    def _write_aria2_cmd(
        self,
        drpid: int,
        folder_path: Path,
        files: list[BtsDownloadFile],
    ) -> None:
        """Export aria2 commands for catalog files still missing on disk."""
        from collectors.UsfsAria2Export import write_drpid_aria2_cmd

        publication_files = [
            (
                self._destination_filename(entry),
                entry.url,
                entry.size_bytes,
            )
            for entry in files
            if not (folder_path / self._destination_filename(entry)).is_file()
        ]
        cmd_path = write_drpid_aria2_cmd(
            drpid,
            folder_path,
            publication_files,
            min_bytes=0,
        )
        if cmd_path:
            Logger.info("Wrote aria2 download commands for DRPID %s: %s", drpid, cmd_path)

    def _destination_filename(self, entry: BtsDownloadFile) -> str:
        """Build a stable on-disk filename for a catalog file entry."""
        if entry.is_main:
            return sanitize_filename(entry.filename)
        stem = sanitize_filename(entry.label)
        suffix = Path(entry.filename).suffix
        if suffix and not stem.lower().endswith(suffix.lower()):
            return f"{stem}{suffix}"
        return stem or sanitize_filename(entry.filename)

    def _folder_inventory(self, folder_path: Path) -> tuple[set[str], int, int]:
        """Return on-disk extensions, total bytes, and file count for a project folder."""
        extensions: set[str] = set()
        total_bytes = 0
        num_files = 0
        if not folder_path.is_dir():
            return extensions, total_bytes, num_files
        for path in folder_path.iterdir():
            if not path.is_file():
                continue
            num_files += 1
            total_bytes += path.stat().st_size
            if path.suffix:
                extensions.add(path.suffix.lstrip(".").lower())
        return extensions, total_bytes, num_files

    def _enrich_extensions_from_archives(
        self,
        drpid: int,
        folder_path: Path,
        extensions: set[str],
    ) -> None:
        """
        Add member extensions from zip archives without changing file counts or sizes.

        Args:
            drpid: Project DRPID for warnings.
            folder_path: Project output directory.
            extensions: Mutable on-disk extension set to augment in place.
        """
        scan = scan_zip_extensions_in_folder(
            folder_path,
            DEFAULT_ZIP_EXTENSION_SCAN_BUDGET,
        )
        extensions.update(scan.extensions)
        for warning in scan.warnings:
            record_warning(drpid, warning)
