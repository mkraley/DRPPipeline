"""
Shared Data.gov catalog collector for DRP Pipeline.

Harvests metadata from catalog.data.gov dataset pages and downloads non-HTML
files. Source-specific wrappers supply agency labels and optional warmup URLs.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from collectors.BtsMetadataExtractor import infer_data_types
from collectors.BudgetedDownload import BudgetedDownload
from collectors.CollectorBase import CollectorBase
from collectors.DataGovArcGisExtent import first_arcgis_extent_from_urls
from collectors.DataGovCoverage import (
    bounding_box_from_spatial,
    looks_like_coordinates,
)
from collectors.DataGovFileDownloader import (
    CATALOG_PDF_NAME,
    DataGovFileDownloader,
    destination_filename,
)
from collectors.DataGovMetadataExtractor import DataGovDownloadFile, parse_catalog_page
from collectors.PlannedFile import PlannedFile
from collectors.UsfsPageDownloader import UsfsPageDownloader
from sourcing.DataGovCandidateFetcher import slug_from_source_url
from utils.Args import Args
from utils.Errors import abort_project, record_error, record_warning
from utils.IcpsrGeographicNormalizer import (
    GeographicNormalizeResult,
    log_geographic_normalization,
    normalize_geographic_metadata,
)
from utils.Logger import Logger
from utils.file_utils import create_output_folder, format_file_size
from utils.inventory_status import STATUS_COLLECTED

_FETCH_TIMEOUT_SEC = 120


class DataGovCollector(CollectorBase):
    """Collect Data.gov catalog metadata and dataset files for one organization."""

    _storage_status_mode = "inventory"

    def __init__(
        self,
        *,
        source_label: str,
        agency: str,
        office: str,
        warmup_url: str | None = None,
        headless: bool = True,
    ) -> None:
        """
        Initialize the collector.

        Args:
            source_label: Short label for log and error messages.
            agency: Agency written onto collected metadata.
            office: Office written onto collected metadata.
            warmup_url: Optional origin to open before downloads (cookies).
            headless: Launch Playwright headless when True.
        """
        label = source_label.strip()
        if not label:
            raise ValueError("source_label is required")
        if not agency.strip() or not office.strip():
            raise ValueError("agency and office are required")
        self._source_label = label
        self._agency = agency
        self._office = office
        self._warmup_url = (warmup_url or "").strip() or None
        self._headless = headless
        self._page_downloader: UsfsPageDownloader | None = None
        self._file_downloader = DataGovFileDownloader()

    def run(self, drpid: int) -> None:
        """
        Run collection for one catalog project.

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
            record_error(
                drpid,
                f"Exception during {self._source_label} collection "
                f"for DRPID {drpid}: {exc}",
            )
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
            record_error(
                drpid,
                f"{self._source_label} page downloader not initialized",
            )
            return {}
        if not self.validate_url(drpid, url):
            return {}
        if slug_from_source_url(url) is None:
            record_error(drpid, f"Not a catalog.data.gov dataset URL: {url}")
            return {}

        parsed = self._fetch_catalog(page_downloader, url, drpid)
        if parsed is None:
            return {}
        self._enrich_geographic_from_arcgis(parsed)
        self._record_geographic_normalization(drpid, parsed)
        if not parsed.get("title"):
            abort_project(
                drpid,
                f"Title not found on {self._source_label} catalog page",
            )
        result = {key: value for key, value in parsed.items() if not key.startswith("_")}

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if folder_path is None:
            record_error(drpid, "Failed to create output folder")
            return result
        result["folder_path"] = str(folder_path)
        if not self._file_downloader.save_catalog_pdf(page_downloader, folder_path, url):
            abort_project(drpid, f"Failed to save catalog PDF: {CATALOG_PDF_NAME}")
        self._download_and_inventory(drpid, page_downloader, folder_path, parsed, result)
        return result

    def _fetch_catalog(
        self,
        page_downloader: UsfsPageDownloader,
        url: str,
        drpid: int,
    ) -> dict[str, Any] | None:
        """Fetch and parse the catalog dataset page."""
        self._warm_session(page_downloader)
        status, body, _content_type, _logical_404 = page_downloader.fetch_page_html(
            url,
            timeout=_FETCH_TIMEOUT_SEC,
        )
        if status != 200 or not body:
            record_error(
                drpid,
                f"Failed to fetch {self._source_label} catalog page "
                f"(status={status}): {url}",
            )
            return None
        return parse_catalog_page(
            body,
            url,
            agency=self._agency,
            office=self._office,
        )

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
            record_error(
                drpid,
                f"No downloadable data files on {self._source_label} catalog page",
            )
            return
        size_cache: dict[str, int | None] = {}
        access_errors: dict[str, str] = {}
        notes = self._file_downloader.save_html_resource_pdfs(
            drpid, page_downloader, folder_path, html_resources
        )
        skipped_large, inventory_bytes, inventory_exts, file_notes, planned = (
            self._download_data_files(
                drpid,
                page_downloader,
                folder_path,
                download_files,
                size_cache,
                access_errors,
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
            access_errors,
            planned,
        )

    def _download_data_files(
        self,
        drpid: int,
        page_downloader: UsfsPageDownloader,
        folder_path: Path,
        download_files: list[DataGovDownloadFile],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str],
    ) -> tuple[bool, int, set[str], list[str], list[PlannedFile]]:
        """Download catalog files, or tally PDF-only inventory when none exist."""
        if not download_files:
            inventory_bytes = self._file_downloader.inventory_bytes(
                page_downloader, folder_path, [], size_cache, access_errors
            )
            return False, inventory_bytes, {"pdf"}, [], []
        notes, skipped_large, inventory_bytes, inventory_exts, planned = (
            self._file_downloader.download_files(
                drpid,
                page_downloader,
                folder_path,
                download_files,
                size_cache,
                access_errors,
            )
        )
        return skipped_large, inventory_bytes, inventory_exts, notes, planned

    def _finish_inventory(
        self,
        drpid: int,
        result: dict[str, Any],
        parsed: dict[str, Any],
        folder_path: Path,
        download_files: list[DataGovDownloadFile],
        html_resources: list[DataGovDownloadFile],
        notes: list[str],
        skipped_large: bool,
        inventory_bytes: int,
        inventory_exts: set[str],
        size_cache: dict[str, int | None],
        access_errors: dict[str, str],
        planned: list[PlannedFile],
    ) -> None:
        """Fill inventory fields after downloads complete."""
        del skipped_large
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
        inventory_files = planned or [
            PlannedFile(
                relative_path=destination_filename(entry),
                source_url=entry.url,
                size_bytes=size_cache.get(entry.url, entry.size_bytes),
                access_error=access_errors.get(entry.url),
            )
            for entry in download_files
        ]
        status = BudgetedDownload().commit_inventory(
            drpid,
            folder_path,
            inventory_files,
        )
        if status != STATUS_COLLECTED:
            result["status"] = status
        result["_skipped_large_file"] = status != STATUS_COLLECTED
        if status != STATUS_COLLECTED:
            self._file_downloader.write_aria2_cmd(
                drpid, folder_path, download_files, size_cache, access_errors
            )
        Logger.info(
            "%s collection complete for DRPID %s: %s files, %s",
            self._source_label,
            drpid,
            result["num_files"],
            result.get("file_size"),
        )

    def _enrich_geographic_from_arcgis(self, parsed: dict[str, Any]) -> None:
        """
        When catalog spatial is missing, infer coverage from ArcGIS service extent.

        MapServer / FeatureServer ``fullExtent`` values are converted to WGS84 and
        normalized through the ICPSR thesaurus (same path as catalog coordinates).
        """
        if parsed.get("geographic_coverage"):
            return
        urls = [
            str(entry.url)
            for entry in list(parsed.get("_download_files") or [])
            + list(parsed.get("_html_resources") or [])
            if getattr(entry, "url", None)
        ]
        bbox = first_arcgis_extent_from_urls(urls)
        if bbox is None:
            return
        geo = normalize_geographic_metadata(bounding_box=bbox)
        if geo.geographic_coverage:
            parsed["geographic_coverage"] = geo.geographic_coverage
        if geo.warnings:
            existing = list(parsed.get("_geographic_warnings") or [])
            existing.extend(geo.warnings)
            parsed["_geographic_warnings"] = existing
        parsed["_raw_spatial"] = (
            f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}"
        )
        parsed["_geographic_bbox"] = bbox

    def _record_geographic_normalization(
        self,
        drpid: int,
        parsed: dict[str, Any],
    ) -> None:
        """Log ICPSR geographic normalization and surface review warnings."""
        raw_spatial = parsed.get("_raw_spatial")
        warnings = list(parsed.get("_geographic_warnings") or [])
        bbox = parsed.get("_geographic_bbox")
        if isinstance(bbox, dict):
            pass
        elif raw_spatial is not None:
            bbox = bounding_box_from_spatial(raw_spatial)
        else:
            bbox = None
        if raw_spatial is None and not warnings and not parsed.get("geographic_coverage"):
            return
        raw_text = str(raw_spatial or "").strip()
        extent = "" if looks_like_coordinates(raw_text) else raw_text
        log_geographic_normalization(
            GeographicNormalizeResult(
                geographic_coverage=str(parsed.get("geographic_coverage") or ""),
                warnings=warnings,
            ),
            geographic_extent_description=extent,
            bounding_box=bbox if isinstance(bbox, dict) else None,
            context=f"DRPID {drpid}",
        )
        for warning in warnings:
            record_warning(drpid, warning)

    def _warm_session(self, page_downloader: UsfsPageDownloader) -> None:
        """Open the warmup origin so cookies are available for file downloads."""
        if self._warmup_url is None:
            return
        page_downloader.fetch_page_html(self._warmup_url, timeout=_FETCH_TIMEOUT_SEC)

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
