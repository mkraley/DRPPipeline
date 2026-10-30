"""
Download Data.gov catalog files with the shared 1 GB collector budget.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

import requests

from collectors.BudgetedDownload import BudgetedDownload
from collectors.ContentLengthProbe import ContentLengthProbe
from collectors.DataGovArcGisExtent import (
    arcgis_json_url,
    is_arcgis_hub_or_item_page,
    is_arcgis_map_or_feature_server,
)
from collectors.DataGovMetadataExtractor import DataGovDownloadFile, filename_from_url
from collectors.PlannedFile import PlannedFile
from collectors.SsaCompleteMetadata import COMPLETE_METADATA_HEADING_SELECTOR
from collectors.UsfsPageDownloader import UsfsPageDownloader
from utils.Errors import abort_project, record_error
from utils.Logger import Logger
from utils.collector_status import pending_download_summary_note
from utils.file_utils import format_file_size, sanitize_filename
from utils.url_utils import requests_verify

CATALOG_PDF_NAME = "catalog_page.pdf"


def destination_filename(entry: DataGovDownloadFile) -> str:
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


def catalog_file_extensions(files: list[DataGovDownloadFile]) -> set[str]:
    """Return extensions for catalog-listed download files plus the catalog PDF."""
    extensions = {"pdf"}
    for entry in files:
        suffix = Path(destination_filename(entry)).suffix
        if suffix:
            extensions.add(suffix.lstrip(".").lower())
    return extensions


class DataGovFileDownloader:
    """Download Data.gov catalog files via Playwright, honoring the 1 GB budget."""

    def download_files(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[DataGovDownloadFile],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str] | None = None,
    ) -> tuple[list[str], bool, int, set[str], list[PlannedFile]]:
        """
        Download catalog files until the cumulative 1 GB budget is reached.

        Args:
            drpid: Project DRPID.
            page_downloader: Playwright helper.
            folder_path: Project output folder.
            files: Catalog file entries.
            size_cache: Mutable URL-to-size map.
            access_errors: Mutable URL-to-access-error map (404/403/…).

        Returns:
            Status notes, large-skip flag, inventory bytes, extensions, and
            planned files (including inaccessible ones).
        """
        notes: list[str] = []
        error_cache = access_errors if access_errors is not None else {}
        planned = self._planned_files(
            page_downloader, files, size_cache, error_cache
        )

        def download_one(item: PlannedFile, dest: Path) -> bool:
            self._log_download(item.filename(), item.size_bytes)
            _written, success = page_downloader.download_file(item.source_url, dest)
            if not success or not dest.is_file():
                record_error(
                    drpid,
                    f"Download failed: {item.filename()} - {item.source_url}",
                )
                notes.append(f"Download failed: {item.filename()} - {item.source_url}")
                return False
            Logger.info("Downloaded: %s", item.filename())
            return True

        outcome = BudgetedDownload().download_until_budget(
            drpid, folder_path, planned, download_one
        )
        notes.extend(outcome.notes)
        summary = self._pending_summary(
            page_downloader, folder_path, files, size_cache, error_cache
        )
        if summary and not outcome.deferred and not any(
            item.access_error for item in planned
        ):
            notes.append(summary)
        inventory_bytes = self.inventory_bytes(
            page_downloader, folder_path, files, size_cache, error_cache
        )
        inventory_exts = catalog_file_extensions(files)
        return notes, outcome.deferred, inventory_bytes, inventory_exts, planned

    def _planned_files(
        self,
        page_downloader: UsfsPageDownloader,
        files: list[DataGovDownloadFile],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str],
    ) -> list[PlannedFile]:
        """Probe sizes and return shared planned-file records."""
        planned: list[PlannedFile] = []
        for entry in files:
            probe = self.probe_entry(
                page_downloader, entry, size_cache, access_errors
            )
            planned.append(
                PlannedFile(
                    relative_path=destination_filename(entry),
                    source_url=entry.url,
                    size_bytes=probe.size_bytes,
                    access_error=probe.access_error,
                )
            )
        return planned

    def probe_entry(
        self,
        page_downloader: UsfsPageDownloader,
        entry: DataGovDownloadFile,
        size_cache: dict[str, int | None],
        access_errors: dict[str, str],
    ) -> ContentLengthProbe:
        """Return catalog size or probed Content-Length / access error."""
        if entry.url in access_errors:
            return ContentLengthProbe(access_error=access_errors[entry.url])
        if entry.url in size_cache:
            return ContentLengthProbe(size_bytes=size_cache[entry.url])
        if entry.size_bytes is not None:
            size_cache[entry.url] = entry.size_bytes
            return ContentLengthProbe(size_bytes=entry.size_bytes)
        probe = page_downloader.probe_download(entry.url)
        if probe.access_error:
            access_errors[entry.url] = probe.access_error
            size_cache[entry.url] = None
            return probe
        size = (
            probe.size_bytes
            if isinstance(probe.size_bytes, int) and probe.size_bytes >= 0
            else None
        )
        size_cache[entry.url] = size
        return ContentLengthProbe(size_bytes=size)

    def expected_bytes(
        self,
        page_downloader: UsfsPageDownloader,
        entry: DataGovDownloadFile,
        size_cache: dict[str, int | None],
        access_errors: dict[str, str] | None = None,
    ) -> int | None:
        """Return catalog or probed Content-Length for a file."""
        error_cache = access_errors if access_errors is not None else {}
        return self.probe_entry(
            page_downloader, entry, size_cache, error_cache
        ).size_bytes

    def inventory_bytes(
        self,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[DataGovDownloadFile],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str] | None = None,
    ) -> int:
        """Estimate total project bytes including files not yet on disk."""
        error_cache = access_errors if access_errors is not None else {}
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
            if entry.url in error_cache:
                continue
            expected = self.expected_bytes(
                page_downloader, entry, size_cache, error_cache
            )
            if expected is not None:
                total_bytes += expected
        total_bytes += _extra_on_disk_bytes(folder_path, known_names)
        return total_bytes

    def write_aria2_cmd(
        self,
        drpid: int,
        folder_path: Path,
        files: list[DataGovDownloadFile],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str] | None = None,
    ) -> None:
        """Export aria2 commands for catalog files still missing on disk."""
        from collectors.UsfsAria2Export import write_drpid_aria2_cmd

        error_cache = access_errors if access_errors is not None else {}
        pending = [
            (
                destination_filename(entry),
                entry.url,
                size_cache.get(entry.url, entry.size_bytes),
            )
            for entry in files
            if entry.url not in error_cache
            and not (folder_path / destination_filename(entry)).is_file()
        ]
        cmd_path = write_drpid_aria2_cmd(drpid, folder_path, pending, min_bytes=0)
        if cmd_path:
            Logger.info("Wrote aria2 download commands for DRPID %s: %s", drpid, cmd_path)

    def _log_download(self, filename: str, expected_bytes: int | None) -> None:
        """Log a download start line."""
        if expected_bytes is not None:
            Logger.info(
                "Downloading file: %s (%s)",
                filename,
                format_file_size(expected_bytes),
            )
            return
        Logger.info("Downloading file: %s", filename)

    def _on_disk_bytes(self, folder_path: Path, files: list[DataGovDownloadFile]) -> int:
        """Return bytes already present for catalog-listed files."""
        total_bytes = 0
        for entry in files:
            dest = folder_path / destination_filename(entry)
            if dest.is_file():
                total_bytes += dest.stat().st_size
        return total_bytes

    def _pending_summary(
        self,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        files: list[DataGovDownloadFile],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str] | None = None,
    ) -> str:
        """Build a status_notes summary for catalog files still missing on disk."""
        error_cache = access_errors if access_errors is not None else {}
        pending = [
            entry
            for entry in files
            if entry.url not in error_cache
            and not (folder_path / destination_filename(entry)).is_file()
        ]
        if not pending:
            return ""
        pending_bytes = 0
        has_unknown = False
        for entry in pending:
            expected = self.expected_bytes(
                page_downloader, entry, size_cache, error_cache
            )
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
        resources: list[DataGovDownloadFile],
    ) -> list[str]:
        """
        Save HTML / ArcGIS resources linked from the catalog page.

        ArcGIS Hub and Geoplatform item pages are printed with SPA-aware waits
        and screen media (default print CSS hides their content). MapServer /
        FeatureServer endpoints are saved as JSON metadata instead of HTML
        directory printouts. Other pages become titled PDFs.
        """
        notes: list[str] = []
        for entry in resources:
            if is_arcgis_map_or_feature_server(entry.url):
                dest = self._save_arcgis_service_json(folder_path, entry)
                if dest is None:
                    abort_project(
                        drpid,
                        f"Failed to save ArcGIS service JSON: {entry.url}",
                    )
                Logger.info("Saved ArcGIS service JSON: %s", dest.name)
                continue
            fallback = Path(filename_from_url(entry.url)).stem or "page"
            dest = page_downloader.url_to_titled_pdf(
                entry.url,
                folder_path,
                fallback_stem=fallback,
                spa_ready=is_arcgis_hub_or_item_page(entry.url),
            )
            if dest is None:
                abort_project(drpid, f"Failed to save HTML resource PDF: {entry.url}")
            Logger.info("Saved HTML resource PDF: %s", dest.name)
        return notes

    def _save_arcgis_service_json(
        self,
        folder_path: Path,
        entry: DataGovDownloadFile,
    ) -> Path | None:
        """
        Download MapServer/FeatureServer ``?f=json`` metadata to the project folder.

        Args:
            folder_path: Project output folder.
            entry: Catalog HTML resource pointing at the service.

        Returns:
            Path to the written JSON file, or None on failure.
        """
        json_url = arcgis_json_url(entry.url)
        dest = folder_path / _arcgis_json_filename(entry.url)
        try:
            response = requests.get(
                json_url,
                timeout=60,
                verify=requests_verify(),
                headers={"Accept": "application/json"},
            )
        except requests.RequestException as exc:
            Logger.error("ArcGIS JSON download failed for %s: %s", json_url, exc)
            return None
        if response.status_code >= 400 or not response.content:
            Logger.error(
                "ArcGIS JSON download HTTP %s for %s",
                response.status_code,
                json_url,
            )
            return None
        dest.write_bytes(response.content)
        return dest


def _arcgis_json_filename(service_url: str) -> str:
    """Build a stable JSON filename from a MapServer/FeatureServer URL path."""
    path = unquote(urlsplit(service_url).path).rstrip("/")
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2:
        stem = "_".join(parts[-2:])
    elif parts:
        stem = parts[-1]
    else:
        stem = "arcgis_service"
    return sanitize_filename(f"{stem}.json")


def _extra_on_disk_bytes(folder_path: Path, known_names: set[str]) -> int:
    """Sum sizes of files in ``folder_path`` not already counted."""
    total_bytes = 0
    if not folder_path.is_dir():
        return total_bytes
    for path in folder_path.iterdir():
        if path.is_file() and path.name not in known_names:
            total_bytes += path.stat().st_size
    return total_bytes
