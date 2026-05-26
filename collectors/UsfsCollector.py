"""
USFS Research Data Archive collector for DRP Pipeline.

Harvests metadata and saves catalog pages (detail, metadata, file index) as PDF,
then downloads publication files listed under "Download all files below".
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Dict

from collectors.UsfsMetadataExtractor import (
    AGENCY,
    OFFICE,
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
from utils.file_utils import (
    create_output_folder,
    folder_extensions_and_size,
    format_file_size,
    sanitize_filename,
)
from utils.url_utils import fetch_page_body, is_valid_url

_HTML_EXTENSIONS = {".html", ".htm"}
_KEEP_EXTENSIONS = {".zip", ".csv", ".xlsx", ".xls"}


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

        status, body, _content_type, _logical_404 = fetch_page_body(url)
        if status != 200 or not body:
            record_error(drpid, f"Failed to fetch USFS detail page (status={status}): {url}")
            return {}

        detail = parse_detail_page(body, url)
        if not detail.get("title"):
            record_warning(drpid, "Title not found on USFS detail page")

        rds_id = rds_id_from_source_url(url)
        metadata: Dict[str, Any] = {}
        if rds_id:
            meta_url = metadata_url_for_rds_id(rds_id)
            meta_status, meta_body, _, _ = fetch_page_body(meta_url)
            if meta_status == 200 and meta_body:
                metadata = parse_metadata_page(meta_body)
            else:
                record_warning(
                    drpid,
                    f"Failed to fetch USFS metadata page (status={meta_status}): {meta_url}",
                )
        else:
            record_warning(drpid, f"Could not extract RDS id from URL: {url}")

        result = merge_usfs_metadata(detail, metadata)
        result["agency"] = AGENCY
        result["office"] = OFFICE

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if not folder_path:
            record_error(drpid, "Failed to create output folder")
            return result

        links = parse_data_access_links(body, url)
        self._save_page_pdfs(drpid, page_downloader, folder_path, url, links)

        for filename, file_url in links.get("publication_files", []):
            self._download_publication_file(drpid, page_downloader, folder_path, filename, file_url)

        exts, total_bytes, num_files = folder_extensions_and_size(folder_path)
        result.update(
            {
                "folder_path": str(folder_path),
                "extensions": ", ".join(exts),
                "file_size": format_file_size(total_bytes),
                "num_files": num_files,
                "download_date": date.today().isoformat(),
            }
        )

        Logger.info(
            "USFS collection complete for DRPID %s: %s files, %s",
            drpid,
            num_files,
            result.get("file_size"),
        )
        return result

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

    def _download_publication_file(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        filename: str,
        file_url: str,
    ) -> None:
        dest = folder_path / sanitize_filename(filename)
        if dest.exists():
            Logger.info("Skipping already-downloaded: %s", dest.name)
            return

        _bytes_written, success = download_via_url(file_url, dest)
        if not success:
            record_warning(drpid, f"Download failed: {file_url}")
            return

        suffix = dest.suffix.lower()
        if suffix in _HTML_EXTENSIONS:
            pdf_dest = dest.with_suffix(".pdf")
            if page_downloader.html_file_to_pdf(dest, pdf_dest):
                dest.unlink(missing_ok=True)
            else:
                record_warning(drpid, f"Failed to convert HTML to PDF: {dest.name}")
        elif suffix and suffix not in _KEEP_EXTENSIONS and suffix != ".pdf":
            Logger.info("Downloaded file kept as-is: %s", dest.name)

    def _update_storage(self, drpid: int, result: Dict[str, Any]) -> None:
        current = Storage.get(drpid)
        if current and current.get("status") == "error":
            result["status"] = "error"
        elif result.get("folder_path") and not result.get("status"):
            result["status"] = "collected"

        update_fields: Dict[str, Any] = {}
        for key, value in result.items():
            if value is None:
                continue
            if value == "":
                continue
            update_fields[key] = value

        if update_fields:
            Storage.update_record(drpid, update_fields)
