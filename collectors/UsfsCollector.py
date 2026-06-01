"""
USFS Research Data Archive collector for DRP Pipeline.

Harvests metadata and saves catalog pages (detail, metadata, file index) as PDF,
then downloads publication files listed under "Download all files below".
Files larger than 1 GB are not downloaded; catalog-listed sizes are still counted.
Catalog entries with only an external-archive data link are noted and skipped similarly.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collectors.UsfsMetadataExtractor import (
    AGENCY,
    OFFICE,
    infer_data_types,
    merge_usfs_metadata,
    metadata_url_for_rds_id,
    parse_data_access_links,
    parse_detail_page,
    parse_metadata_page,
    rds_id_from_source_url,
)
from collectors.UsfsPageDownloader import UsfsPageDownloader
from storage import Storage
from utils.Args import Args
from utils.Errors import record_error, record_warning
from utils.Logger import Logger
from utils.download_with_progress import download_via_url
from utils.file_utils import create_output_folder, format_file_size, sanitize_filename
from utils.IcpsrGeographicNormalizer import (
    log_geographic_normalization,
    normalize_geographic_metadata,
)
from utils.url_utils import fetch_page_body, is_valid_url

PublicationFile = Tuple[str, str, Optional[int]]

_HTML_EXTENSIONS = {".html", ".htm"}
_KEEP_EXTENSIONS = {".zip", ".csv", ".xlsx", ".xls"}
MAX_DOWNLOAD_BYTES = 1 * 1024**3  # 1 GB
TOTAL_SIZE_WARN_BYTES = 50 * 1024**3  # 50 GB
_DOWNLOAD_TIMEOUT_SEC = 3600  # 1 hour read timeout for large-but-allowed files
_PDF_NAMES = ("catalog_detail.pdf", "metadata.pdf", "file_index.pdf")
STATUS_COLLECTED_LARGE_FILE = "collected - large file"
STATUS_COLLECTED_EXTERNAL_ARCHIVE = "collected - external archive"
STATUS_UPLOADED_LARGE_FILE = "uploaded - large file"
# FGDC parse fields kept in memory only; Storage has geographic_coverage instead.
_METADATA_KEYS_NOT_IN_STORAGE = frozenset({
    "geographic_extent_description",
    "place_keywords",
    "bounding_box",
})
_USFS_HOST = "fs.usda.gov"


def _fetch_usfs_page_body(
    url: str,
    page_downloader: UsfsPageDownloader,
    *,
    timeout: int = 60,
) -> Tuple[int, str, Optional[str], bool]:
    """
    Fetch USFS catalog HTML; fall back to Playwright when HTTP/curl fails.

    fs.usda.gov often fails certificate verification under curl_cffi/requests on
    Windows even though a real browser works fine.
    """
    status, body, content_type, logical_404 = fetch_page_body(url, timeout=timeout)
    if status == 200 and body:
        return status, body, content_type, logical_404
    Logger.warning(
        "HTTP fetch failed (status=%s) for %s; using Playwright browser",
        status,
        url,
    )
    return page_downloader.fetch_page_html(url, timeout=timeout)


class UsfsCollector:
    """Collect USFS RDS catalog metadata and publication files."""

    def __init__(self, headless: bool = True) -> None:
        self._headless = headless

    def run(self, drpid: int) -> None:
        """
        Run the collector for a single project (ModuleProtocol interface).

        Args:
            drpid: The DRPID of the project to process.
        """
        record = Storage.get(drpid)
        if record is None:
            record_error(drpid, f"Project record not found for DRPID: {drpid}", update_storage=False)
            return

        source_url = record.get("source_url")
        if not source_url:
            record_error(drpid, f"Missing source_url for DRPID: {drpid}")
            return

        page_downloader = UsfsPageDownloader(headless=self._headless)
        try:
            result = self._collect(source_url, drpid, page_downloader)
            self._update_storage(drpid, result)
        except Exception as exc:
            record_error(drpid, f"Exception during USFS collection for DRPID {drpid}: {exc}")
        finally:
            page_downloader.close()

    def _collect(
        self,
        url: str,
        drpid: int,
        page_downloader: UsfsPageDownloader,
    ) -> Dict[str, Any]:
        if not is_valid_url(url):
            record_error(drpid, f"Invalid URL: {url}")
            return {}

        if "fs.usda.gov/rds/archive/catalog/" not in url:
            record_error(drpid, f"Not a USFS RDS catalog URL: {url}")
            return {}

        status, body, _content_type, _logical_404 = _fetch_usfs_page_body(url, page_downloader)
        if status != 200 or not body:
            record_error(drpid, f"Failed to fetch USFS detail page (status={status}): {url}")
            return {}

        detail = parse_detail_page(body, url)
        if not detail.get("title"):
            record_warning(drpid, "Title not found on USFS detail page")

        rds_id = rds_id_from_source_url(url)
        metadata: Dict[str, Any] = {}
        meta_body = ""
        if rds_id:
            meta_url = metadata_url_for_rds_id(rds_id)
            meta_status, meta_body, _, _ = _fetch_usfs_page_body(meta_url, page_downloader)
            if meta_status == 200 and meta_body:
                metadata = parse_metadata_page(meta_body)
            else:
                record_warning(
                    drpid,
                    f"Failed to fetch USFS metadata page (status={meta_status}): {meta_url}",
                )
        else:
            record_warning(drpid, f"Could not extract RDS id from URL: {url}")

        # Geographic coverage uses FGDC metadata HTML (above), before publication downloads.
        result = merge_usfs_metadata(detail, metadata)
        data_types = infer_data_types(
            result.get("title", ""),
            result.get("summary", ""),
            meta_body,
        )
        if data_types:
            result["data_types"] = data_types
        self._apply_geographic_coverage(drpid, result, metadata)
        result["agency"] = AGENCY
        result["office"] = OFFICE

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if not folder_path:
            record_error(drpid, "Failed to create output folder")
            return result

        links = parse_data_access_links(body, url)
        self._save_page_pdfs(drpid, page_downloader, folder_path, url, links)

        external_archive_url = links.get("external_archive_url", "")
        publication_files = links.get("publication_files", [])
        external_archive_only = bool(
            external_archive_url and not publication_files
        )

        if external_archive_only:
            record_warning(
                drpid,
                f"Data available via external archive (not downloaded): {external_archive_url}",
            )

        status_notes, inventory_bytes, inventory_exts, skipped_large = self._process_publication_files(
            drpid,
            page_downloader,
            folder_path,
            publication_files,
        )

        if external_archive_only:
            status_notes.append(
                f"External archive (not downloaded): {external_archive_url}"
            )

        pdf_bytes = self._pdf_folder_bytes(folder_path)
        total_bytes = inventory_bytes + pdf_bytes
        all_exts = sorted(inventory_exts | {"pdf"})
        num_files = len(publication_files) + len(_PDF_NAMES)

        notes_parts = list(status_notes)
        if total_bytes > TOTAL_SIZE_WARN_BYTES:
            notes_parts.insert(
                0,
                f"TOTAL SIZE EXCEEDS 50 GB: {format_file_size(total_bytes)} "
                f"({num_files} files including items not downloaded; manual download may be required).",
            )

        result.update(
            {
                "folder_path": str(folder_path),
                "extensions": ", ".join(all_exts),
                "file_size": format_file_size(total_bytes),
                "num_files": num_files,
                "download_date": date.today().isoformat(),
            }
        )
        if notes_parts:
            result["status_notes"] = "\n".join(notes_parts)

        result["_skipped_large_file"] = skipped_large
        result["_external_archive"] = external_archive_only
        if skipped_large:
            from collectors.UsfsAria2Export import write_drpid_aria2_cmd

            cmd_path = write_drpid_aria2_cmd(
                drpid,
                folder_path,
                links.get("publication_files", []),
            )
            if cmd_path:
                Logger.info(
                    "Wrote aria2 download commands for DRPID %s: %s",
                    drpid,
                    cmd_path,
                )

        Logger.info(
            "USFS collection complete for DRPID %s: %s files, %s",
            drpid,
            num_files,
            result.get("file_size"),
        )
        return result

    def _apply_geographic_coverage(
        self,
        drpid: int,
        result: Dict[str, Any],
        metadata: Dict[str, Any],
    ) -> None:
        """Map FGDC geographic fields to ICPSR thesaurus terms on ``result``."""
        geo = normalize_geographic_metadata(
            geographic_extent_description=metadata.get("geographic_extent_description", ""),
            place_keywords=metadata.get("place_keywords"),
            bounding_box=metadata.get("bounding_box"),
        )
        log_geographic_normalization(
            geo,
            geographic_extent_description=metadata.get("geographic_extent_description", ""),
            place_keywords=metadata.get("place_keywords"),
            bounding_box=metadata.get("bounding_box"),
            context=f"DRPID {drpid}",
        )
        if geo.geographic_coverage:
            result["geographic_coverage"] = geo.geographic_coverage
        for warning in geo.warnings:
            record_warning(drpid, warning)

    def _save_page_pdfs(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        catalog_url: str,
        links: dict[str, Any],
    ) -> None:
        pages = [
            ("catalog_detail.pdf", catalog_url),
            ("metadata.pdf", links.get("metadata_url", "")),
            ("file_index.pdf", links.get("fileindex_url", "")),
        ]
        for pdf_name, page_url in pages:
            if not page_url:
                record_warning(drpid, f"Missing URL for {pdf_name}")
                continue
            dest = folder_path / pdf_name
            if not page_downloader.url_to_pdf(page_url, dest):
                record_warning(drpid, f"Failed to save PDF: {pdf_name}")

    def _process_publication_files(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader | None,
        folder_path: Path,
        publication_files: List[PublicationFile],
        *,
        download: bool = True,
    ) -> Tuple[List[str], int, set[str], bool]:
        """
        Inventory publication files using catalog sizes; optionally download.

        Returns:
            (status_note_lines, total_bytes_for_inventory, extensions_set, skipped_large)
        """
        notes: List[str] = []
        total_bytes = 0
        exts: set[str] = set()
        skipped_large = False

        for filename, file_url, catalog_bytes in publication_files:
            dest = folder_path / sanitize_filename(filename)
            if dest.suffix:
                exts.add(dest.suffix.lstrip(".").lower())

            inventory_bytes = catalog_bytes
            if inventory_bytes is None and dest.exists():
                inventory_bytes = dest.stat().st_size

            if dest.exists():
                disk_bytes = dest.stat().st_size
                total_bytes += inventory_bytes if inventory_bytes is not None else disk_bytes
                limit = inventory_bytes if inventory_bytes is not None else disk_bytes
                if limit > MAX_DOWNLOAD_BYTES:
                    notes.append(
                        f"On disk (>1GB): {dest.name} ({format_file_size(limit)})"
                    )
                continue

            if inventory_bytes is not None and inventory_bytes > MAX_DOWNLOAD_BYTES:
                total_bytes += inventory_bytes
                skipped_large = True
                notes.append(
                    f"Skipped download (>1GB): {filename} ({format_file_size(inventory_bytes)}) - "
                    f"download manually: {file_url}"
                )
                continue

            if not download:
                if inventory_bytes is not None:
                    total_bytes += inventory_bytes
                continue

            counted_catalog = False
            if inventory_bytes is not None:
                total_bytes += inventory_bytes
                counted_catalog = True

            success = False
            _bytes_written = 0
            if inventory_bytes is not None:
                Logger.info(
                    "Downloading publication file: %s (%s)",
                    filename,
                    format_file_size(inventory_bytes),
                )
            else:
                Logger.info("Downloading publication file: %s", filename)
            if page_downloader is not None and _USFS_HOST in file_url:
                _bytes_written, success = page_downloader.download_file(file_url, dest)
            if not success:
                if inventory_bytes is not None:
                    Logger.info(
                        "HTTP download starting: %s (%s)",
                        filename,
                        format_file_size(inventory_bytes),
                    )
                else:
                    Logger.info("HTTP download starting: %s", filename)
                _bytes_written, success = download_via_url(
                    file_url, dest, timeout_sec=_DOWNLOAD_TIMEOUT_SEC
                )
            if success and dest.is_file():
                Logger.info("Downloaded publication file: %s", filename)
            if not success:
                Logger.info("Publication file download failed: %s", filename)
            if not success:
                if counted_catalog and inventory_bytes is not None:
                    total_bytes -= inventory_bytes
                record_error(drpid, f"Download failed: {filename} - {file_url}")
                notes.append(f"Download failed: {filename} - {file_url}")
                continue

            suffix = dest.suffix.lower()
            if suffix in _HTML_EXTENSIONS:
                pdf_dest = dest.with_suffix(".pdf")
                if page_downloader and page_downloader.html_file_to_pdf(dest, pdf_dest):
                    dest.unlink(missing_ok=True)
                    dest = pdf_dest
                    if dest.suffix:
                        exts.add(dest.suffix.lstrip(".").lower())
                else:
                    record_warning(drpid, f"Failed to convert HTML to PDF: {dest.name}")
            elif suffix and suffix not in _KEEP_EXTENSIONS and suffix != ".pdf":
                Logger.info("Downloaded file kept as-is: %s", dest.name)

            if dest.exists():
                actual = dest.stat().st_size
                if counted_catalog and inventory_bytes is not None:
                    total_bytes += actual - inventory_bytes
                elif not counted_catalog:
                    total_bytes += actual

        return notes, total_bytes, exts, skipped_large

    def _pdf_folder_bytes(self, folder_path: Path) -> int:
        total = 0
        for name in _PDF_NAMES:
            path = folder_path / name
            if path.is_file():
                total += path.stat().st_size
        return total

    def _update_storage(self, drpid: int, result: Dict[str, Any]) -> None:
        current = Storage.get(drpid) or {}
        skipped_large = bool(result.pop("_skipped_large_file", False))
        external_archive = bool(result.pop("_external_archive", False))
        has_errors = bool((current.get("errors") or "").strip())

        if has_errors:
            result.pop("status", None)
        elif result.get("folder_path"):
            if skipped_large:
                result["status"] = STATUS_COLLECTED_LARGE_FILE
            elif external_archive:
                result["status"] = STATUS_COLLECTED_EXTERNAL_ARCHIVE
            else:
                result["status"] = "collected"

        update_fields: Dict[str, Any] = {}
        for key, value in result.items():
            if key in _METADATA_KEYS_NOT_IN_STORAGE:
                continue
            if value is None:
                continue
            if value == "":
                continue
            update_fields[key] = value

        if update_fields:
            Storage.update_record(drpid, update_fields)
