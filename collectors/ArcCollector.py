"""
Ag Data Commons (ARC) collector for DRP Pipeline.

Downloads dataset files via the public Figshare API (and Dryad/Zenodo when
applicable). Files larger than 1 GB are not downloaded; their filenames are
recorded in ``status_notes`` for manual retrieval (USFS pattern).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from collectors.ArcCatalogHtmlBuilder import build_catalog_html
from collectors.ArcMetadataExtractor import extract_metadata
from sourcing.ArcApiClient import ArcApiClient, article_id_from_source_url
from sourcing.ArcCandidateFetcher import AGENCY, OFFICE
from sourcing.ArcFileInventory import MAX_DOWNLOAD_BYTES, ArcFileInventory
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
from utils.url_utils import is_valid_url

_DOWNLOAD_TIMEOUT_SEC = 3600
_CATALOG_PDF_NAME = "catalog_detail.pdf"
_CATALOG_HTML_NAME = "catalog_detail.html"
_METADATA_JSON_NAME = "arc_metadata.json"
STATUS_COLLECTED_LARGE_FILE = "collected - large file"
STATUS_COLLECTED_EXTERNAL_ARCHIVE = "collected - external archive"
_ARC_URL_FRAGMENT = "agdatacommons.nal.usda.gov"
_EXTENSION_CATALOG_PDF_HINT = (
    "Catalog PDF: open this project in the Interactive Collector, use Copy & Open, "
    f"then click Save as PDF on the ADC item page (writes {_CATALOG_PDF_NAME})."
)


class ArcCollector:
    """Collect ARC datasets via the Figshare public API."""

    def __init__(
        self,
        *,
        api_client: ArcApiClient | None = None,
        inventory: ArcFileInventory | None = None,
    ) -> None:
        """
        Initialize the collector.

        Args:
            api_client: Figshare API client (created when omitted).
            inventory: File inventory helper (created when omitted).
        """
        self._api = api_client or ArcApiClient()
        self._inventory = inventory or ArcFileInventory()

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

        try:
            result = self._collect(source_url, drpid)
            self._update_storage(drpid, result)
        except Exception as exc:
            record_error(drpid, f"Exception during ARC collection for DRPID {drpid}: {exc}")

    def _collect(
        self,
        url: str,
        drpid: int,
    ) -> dict[str, Any]:
        """Fetch metadata and download files for one ARC dataset."""
        if not is_valid_url(url):
            record_error(drpid, f"Invalid URL: {url}")
            return {}

        if _ARC_URL_FRAGMENT not in url:
            record_error(drpid, f"Not an Ag Data Commons URL: {url}")
            return {}

        article_id = article_id_from_source_url(url)
        if article_id is None:
            record_error(drpid, f"Could not extract Figshare article ID from URL: {url}")
            return {}

        article = self._api.fetch_article(article_id)
        result: dict[str, Any] = extract_metadata(article)
        self._record_geo_warnings(drpid, result)
        result["agency"] = AGENCY
        result["office"] = OFFICE

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if not folder_path:
            record_error(drpid, "Failed to create output folder")
            return result

        self._save_metadata_json(folder_path, article)
        self._save_catalog_pdf(drpid, folder_path, article, url)

        files = self._inventory.list_files_for_article(article)
        _num_files, _file_size, _extensions, _has_large, has_unresolved, all_unresolved = (
            self._inventory.summarize_inventory(files)
        )

        if all_unresolved:
            external_url = files[0]["url"] if files else url
            record_warning(
                drpid,
                f"Data available via external link (not downloaded): {external_url}",
            )
            result.update(self._folder_summary(folder_path))
            result["download_date"] = date.today().isoformat()
            result["_external_archive"] = True
            return result

        if has_unresolved:
            record_warning(drpid, "Some external data links could not be expanded via API.")

        status_notes, _total_bytes, _exts, skipped_large = self._process_files(
            drpid,
            folder_path,
            files,
        )

        result.update(self._folder_summary(folder_path))
        result["download_date"] = date.today().isoformat()
        result["_skipped_large_file"] = skipped_large
        result["_external_archive"] = False
        if status_notes:
            result["status_notes"] = "\n".join(status_notes)

        if skipped_large:
            self._write_aria2_cmd(drpid, folder_path, files)

        Logger.info(
            "ARC collection complete for DRPID %s: %s files, %s",
            drpid,
            result.get("num_files"),
            result.get("file_size"),
        )
        return result

    def _record_geo_warnings(self, drpid: int, result: dict[str, Any]) -> None:
        """Surface geographic normalization warnings via Storage."""
        for warning in result.pop("_geo_warnings", []) or []:
            record_warning(drpid, warning)

    def _save_catalog_pdf(
        self,
        drpid: int,
        folder_path: Path,
        article: dict[str, Any],
        source_url: str,
    ) -> None:
        """Save API catalog HTML; portal PDF comes from the browser extension."""
        html_path = folder_path / _CATALOG_HTML_NAME
        pdf_path = folder_path / _CATALOG_PDF_NAME

        html_path.write_text(build_catalog_html(article, source_url), encoding="utf-8")
        if pdf_path.is_file() and pdf_path.stat().st_size > 0:
            Logger.info("ARC catalog PDF already present for DRPID %s", drpid)
            return
        record_warning(drpid, _EXTENSION_CATALOG_PDF_HINT)

    def _save_metadata_json(self, folder_path: Path, article: dict[str, Any]) -> None:
        """Persist the Figshare article JSON alongside downloaded files."""
        dest = folder_path / _METADATA_JSON_NAME
        dest.write_text(json.dumps(article, indent=2), encoding="utf-8")

    def _folder_summary(self, folder_path: Path) -> dict[str, Any]:
        """Summarize on-disk files for Storage numeric fields."""
        extensions, total_bytes, num_files = folder_extensions_and_size(folder_path)
        return {
            "folder_path": str(folder_path),
            "num_files": num_files,
            "file_size": format_file_size(total_bytes),
            "extensions": ", ".join(extensions),
        }

    def _process_files(
        self,
        drpid: int,
        folder_path: Path,
        files: list[dict[str, Any]],
    ) -> tuple[list[str], int, set[str], bool]:
        """
        Download inventory files; skip those over 1 GB.

        Returns:
            Tuple of (status_note_lines for >1GB skips only, total_bytes, extensions, skipped_large).
        """
        notes: list[str] = []
        total_bytes = 0
        exts: set[str] = set()
        skipped_large = False

        for file_row in files:
            source = str(file_row.get("source") or "")
            if source == "external-unresolved":
                continue

            filename = str(file_row.get("name") or "file")
            file_url = str(file_row.get("url") or "")
            size_bytes = file_row.get("size_bytes")
            catalog_bytes = size_bytes if isinstance(size_bytes, int) else None

            dest = folder_path / sanitize_filename(filename)
            if dest.suffix:
                exts.add(dest.suffix.lstrip(".").lower())

            if dest.exists():
                disk_bytes = dest.stat().st_size
                total_bytes += catalog_bytes if catalog_bytes is not None else disk_bytes
                continue

            if catalog_bytes is not None and catalog_bytes > MAX_DOWNLOAD_BYTES:
                total_bytes += catalog_bytes
                skipped_large = True
                notes.append(
                    f"Skipped download (>1GB): {filename} ({format_file_size(catalog_bytes)}) - "
                    f"download manually: {file_url}"
                )
                continue

            if not file_url:
                record_error(drpid, f"Missing download URL for file: {filename}")
                continue

            Logger.info("Downloading ARC file: %s", filename)
            _bytes_written, success = download_via_url(
                file_url,
                dest,
                timeout_sec=_DOWNLOAD_TIMEOUT_SEC,
            )
            if not success:
                record_error(drpid, f"Download failed: {filename} - {file_url}")
                continue

            if dest.exists():
                total_bytes += dest.stat().st_size
                Logger.info("Downloaded ARC file: %s", filename)

        return notes, total_bytes, exts, skipped_large

    def _write_aria2_cmd(
        self,
        drpid: int,
        folder_path: Path,
        files: list[dict[str, Any]],
    ) -> None:
        """Export aria2 commands for skipped large files."""
        from collectors.ArcAria2Export import write_drpid_aria2_cmd

        inventory_files = [
            (
                str(file_row.get("name") or "file"),
                str(file_row.get("url") or ""),
                file_row.get("size_bytes") if isinstance(file_row.get("size_bytes"), int) else None,
            )
            for file_row in files
        ]
        cmd_path = write_drpid_aria2_cmd(drpid, folder_path, inventory_files)
        if cmd_path:
            Logger.info("Wrote aria2 download commands for DRPID %s: %s", drpid, cmd_path)

    def _update_storage(self, drpid: int, result: dict[str, Any]) -> None:
        """Apply collection results to Storage."""
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

        update_fields: dict[str, Any] = {}
        for key, value in result.items():
            if value is None or value == "":
                continue
            update_fields[key] = value

        if update_fields:
            Storage.update_record(drpid, update_fields)
