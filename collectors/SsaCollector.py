"""
Social Security Administration collector for DRP Pipeline.

Harvests metadata from catalog.data.gov dataset pages and downloads non-HTML
files from ssa.gov. Akamai blocks plain HTTP, so Playwright is used.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from collectors.BtsMetadataExtractor import infer_data_types
from collectors.CollectorBase import CollectorBase
from collectors.SsaFileDownloader import CATALOG_PDF_NAME, SsaFileDownloader
from collectors.SsaMetadataExtractor import SsaDownloadFile, parse_catalog_page
from collectors.UsfsPageDownloader import UsfsPageDownloader
from sourcing.SsaCandidateFetcher import slug_from_source_url
from utils.Args import Args
from utils.Errors import record_error, record_warning
from utils.Logger import Logger
from utils.file_utils import create_output_folder, format_file_size

_FETCH_TIMEOUT_SEC = 120
_SSA_WARMUP_URL = "https://www.ssa.gov/data/"


class SsaCollector(CollectorBase):
    """Collect SSA catalog metadata and dataset files."""

    _storage_status_mode = "inventory"

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize the collector.

        Args:
            headless: Launch Playwright headless when True.
        """
        self._headless = headless
        self._page_downloader: UsfsPageDownloader | None = None
        self._file_downloader = SsaFileDownloader()

    def run(self, drpid: int) -> None:
        """
        Run collection for one SSA project.

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
            record_error(drpid, f"Exception during SSA collection for DRPID {drpid}: {exc}")
        finally:
            self._page_downloader.close()
            self._page_downloader = None

    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Collect one catalog dataset page and its file downloads."""
        del record
        page_downloader = self._page_downloader
        if page_downloader is None:
            record_error(drpid, "SSA page downloader not initialized")
            return {}
        if not self.validate_url(drpid, url):
            return {}
        if slug_from_source_url(url) is None:
            record_error(drpid, f"Not a catalog.data.gov dataset URL: {url}")
            return {}

        parsed = self._fetch_catalog(page_downloader, url, drpid)
        if parsed is None:
            return {}
        if not parsed.get("title"):
            record_warning(drpid, "Title not found on SSA catalog page")
        result = {key: value for key, value in parsed.items() if not key.startswith("_")}

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if folder_path is None:
            record_error(drpid, "Failed to create output folder")
            return result
        result["folder_path"] = str(folder_path)
        if not self._file_downloader.save_catalog_pdf(page_downloader, folder_path, url):
            record_warning(drpid, f"Failed to save catalog PDF: {CATALOG_PDF_NAME}")
        self._download_and_inventory(drpid, page_downloader, folder_path, parsed, result)
        return result

    def _fetch_catalog(
        self,
        page_downloader: UsfsPageDownloader,
        url: str,
        drpid: int,
    ) -> dict[str, Any] | None:
        """Fetch and parse the catalog dataset page."""
        self._warm_ssa_session(page_downloader)
        status, body, _content_type, _logical_404 = page_downloader.fetch_page_html(
            url,
            timeout=_FETCH_TIMEOUT_SEC,
        )
        if status != 200 or not body:
            record_error(drpid, f"Failed to fetch SSA catalog page (status={status}): {url}")
            return None
        return parse_catalog_page(body, url)

    def _download_and_inventory(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        parsed: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        """Download files and fill inventory fields."""
        download_files = parsed.get("_download_files") or []
        html_resources = parsed.get("_html_resources") or []
        if not download_files and not html_resources:
            record_error(drpid, "No downloadable data files on SSA catalog page")
            return
        size_cache: dict[str, int | None] = {}
        notes = self._file_downloader.save_html_resource_pdfs(
            drpid, page_downloader, folder_path, html_resources
        )
        skipped_large, inventory_bytes, inventory_exts, file_notes = (
            self._download_data_files(
                drpid, page_downloader, folder_path, download_files, size_cache
            )
        )
        notes.extend(file_notes)
        self._finish_inventory(
            drpid,
            result,
            parsed,
            folder_path,
            download_files,
            html_resources,
            notes,
            skipped_large,
            inventory_bytes,
            inventory_exts,
            size_cache,
        )

    def _download_data_files(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        download_files: list[SsaDownloadFile],
        size_cache: dict[str, int | None],
    ) -> tuple[bool, int, set[str], list[str]]:
        """Download catalog files, or tally PDF-only inventory when none exist."""
        if not download_files:
            inventory_bytes = self._file_downloader.inventory_bytes(
                page_downloader, folder_path, [], size_cache
            )
            return False, inventory_bytes, {"pdf"}, []
        notes, skipped_large, inventory_bytes, inventory_exts = (
            self._file_downloader.download_files(
                drpid, page_downloader, folder_path, download_files, size_cache
            )
        )
        return skipped_large, inventory_bytes, inventory_exts, notes

    def _finish_inventory(
        self,
        drpid: int,
        result: dict[str, Any],
        parsed: dict[str, Any],
        folder_path: Path,
        download_files: list[SsaDownloadFile],
        html_resources: list[SsaDownloadFile],
        notes: list[str],
        skipped_large: bool,
        inventory_bytes: int,
        inventory_exts: set[str],
        size_cache: dict[str, int | None],
    ) -> None:
        """Fill inventory fields after downloads complete."""
        extensions = set(inventory_exts)
        on_disk_exts, _bytes, _count = self._folder_inventory(folder_path)
        extensions.update(on_disk_exts)
        if extensions:
            result["extensions"] = ", ".join(sorted(extensions))
        result["num_files"] = 1 + len(html_resources) + len(download_files)
        result["file_size"] = format_file_size(inventory_bytes)
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
        if notes:
            result["status_notes"] = "\n".join(notes)
        result["_skipped_large_file"] = skipped_large
        if skipped_large:
            self._file_downloader.write_aria2_cmd(drpid, folder_path, download_files, size_cache)
        Logger.info(
            "SSA collection complete for DRPID %s: %s files, %s",
            drpid,
            result["num_files"],
            result.get("file_size"),
        )

    def _warm_ssa_session(self, page_downloader: UsfsPageDownloader) -> None:
        """Open ssa.gov once so Akamai cookies are available for file downloads."""
        page_downloader.fetch_page_html(_SSA_WARMUP_URL, timeout=_FETCH_TIMEOUT_SEC)

    def _folder_inventory(self, folder_path: Path) -> tuple[set[str], int, int]:
        """Return on-disk extensions, total bytes, and file count."""
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
