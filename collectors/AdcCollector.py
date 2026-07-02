"""
Ag Data Commons (ADC) collector for DRP Pipeline.

Downloads Figshare-hosted dataset files via the public Figshare API. Records
with external-only storage (link-only or DOI placeholders) save catalog metadata
only and set status ``collected - external archive``. Files larger than 1 GB are
not downloaded; their filenames are recorded in ``status_notes``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from collectors.AdcCatalogHtmlBuilder import build_catalog_html
from collectors.AdcMetadataExtractor import extract_metadata
from sourcing.AdcApiClient import AdcApiClient, article_id_from_source_url
from sourcing.AdcCandidateFetcher import AGENCY, OFFICE
from sourcing.AdcFileInventory import MAX_DOWNLOAD_BYTES, AdcFileInventory
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
from utils.retry_http import (
    DEFAULT_BACKOFF_SECONDS,
    DEFAULT_MAX_RETRIES,
    SourceNotFoundError,
    download_with_retry,
    retry_http_call,
)
from utils.url_utils import is_valid_url

_DOWNLOAD_TIMEOUT_SEC = 3600
_CATALOG_HTML_NAME = "catalog_detail.html"
_METADATA_JSON_NAME = "adc_metadata.json"
STATUS_COLLECTED_LARGE_FILE = "collected - large file"
STATUS_COLLECTED_EXTERNAL_ARCHIVE = "collected - external archive"
STATUS_NOT_FOUND = "not_found"
_ADC_URL_FRAGMENT = "agdatacommons.nal.usda.gov"


class AdcCollector:
    """Collect ADC datasets via the Figshare public API."""

    def __init__(
        self,
        *,
        api_client: AdcApiClient | None = None,
        inventory: AdcFileInventory | None = None,
        fetch_retries: int = DEFAULT_MAX_RETRIES,
        download_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        """
        Initialize the collector.

        Args:
            api_client: Figshare API client (created when omitted).
            inventory: File inventory helper (created when omitted).
            fetch_retries: Retries for Figshare article metadata requests.
            download_retries: Retries for individual file downloads.
            retry_backoff: Base seconds for exponential backoff between retries.
        """
        self._api = api_client or AdcApiClient()
        self._inventory = inventory or AdcFileInventory()
        self._fetch_retries = fetch_retries
        self._download_retries = download_retries
        self._retry_backoff = retry_backoff

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
        except SourceNotFoundError as exc:
            record_error(
                drpid,
                f"ADC source not accessible for DRPID {drpid}: {exc}",
                status_value=STATUS_NOT_FOUND,
            )
        except Exception as exc:
            record_error(drpid, f"Exception during ADC collection for DRPID {drpid}: {exc}")

    def _collect(
        self,
        url: str,
        drpid: int,
    ) -> dict[str, Any]:
        """Fetch metadata and download Figshare-hosted files for one ADC dataset."""
        if not is_valid_url(url):
            record_error(drpid, f"Invalid URL: {url}")
            return {}

        if _ADC_URL_FRAGMENT not in url:
            record_error(drpid, f"Not an Ag Data Commons URL: {url}")
            return {}

        article_id = article_id_from_source_url(url)
        if article_id is None:
            record_error(drpid, f"Could not extract Figshare article ID from URL: {url}")
            return {}

        article = self._fetch_article_with_retry(article_id)
        result: dict[str, Any] = extract_metadata(article)
        self._record_geo_warnings(drpid, result)
        result["agency"] = AGENCY
        result["office"] = OFFICE

        folder_path = create_output_folder(Path(Args.base_output_dir), drpid)
        if not folder_path:
            record_error(drpid, "Failed to create output folder")
            return result

        self._save_metadata_json(folder_path, article)
        self._save_catalog_html(folder_path, article, url)

        if self._inventory.is_external_archive(article):
            result.update(self._folder_summary(folder_path))
            result["download_date"] = date.today().isoformat()
            result["_external_archive"] = True
            external_note = self._inventory.external_archive_status_note(article)
            if external_note:
                result["status_notes"] = external_note
            return result

        files = self._inventory.list_figshare_hosted_files(article)
        status_notes, inventory_bytes, inventory_exts, skipped_large = self._process_files(
            drpid,
            folder_path,
            files,
        )

        result.update(
            self._collection_summary(folder_path, files, inventory_bytes, inventory_exts)
        )
        result["download_date"] = date.today().isoformat()
        result["_skipped_large_file"] = skipped_large
        result["_external_archive"] = False
        if status_notes:
            result["status_notes"] = "\n".join(status_notes)

        if skipped_large:
            self._write_aria2_cmd(drpid, folder_path, files)

        Logger.info(
            "ADC collection complete for DRPID %s: %s files, %s",
            drpid,
            result.get("num_files"),
            result.get("file_size"),
        )
        return result

    def _fetch_article_with_retry(self, article_id: int) -> dict[str, Any]:
        """
        Fetch Figshare article metadata with retries on transient HTTP errors.

        Args:
            article_id: Figshare article ID.

        Returns:
            Article JSON document.

        Raises:
            SourceNotFoundError: When the article is not found (404/410).
            requests.HTTPError: When metadata fetch fails after retries.
        """
        return retry_http_call(
            lambda: self._api.fetch_article(article_id),
            max_retries=self._fetch_retries,
            base_delay=self._retry_backoff,
            operation_label=f"Figshare article {article_id}",
        )

    def _record_geo_warnings(self, drpid: int, result: dict[str, Any]) -> None:
        """Surface geographic normalization warnings via Storage."""
        for warning in result.pop("_geo_warnings", []) or []:
            record_warning(drpid, warning)

    def _save_catalog_html(
        self,
        folder_path: Path,
        article: dict[str, Any],
        source_url: str,
    ) -> None:
        """Save a plain HTML catalog snapshot built from Figshare API metadata."""
        html_path = folder_path / _CATALOG_HTML_NAME
        html_path.write_text(build_catalog_html(article, source_url), encoding="utf-8")
        Logger.info("Wrote ADC catalog HTML: %s", html_path)

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

    def _collection_summary(
        self,
        folder_path: Path,
        files: list[dict[str, Any]],
        inventory_bytes: int,
        inventory_exts: set[str],
    ) -> dict[str, Any]:
        """
        Build Storage file stats including skipped large inventory files.

        Args:
            folder_path: Project output directory.
            files: Figshare-hosted inventory rows processed for download.
            inventory_bytes: Byte total from ``_process_files`` (includes skipped >1GB).
            inventory_exts: Extensions seen in the inventory pass.

        Returns:
            ``folder_path``, ``num_files``, ``file_size``, and ``extensions``.
        """
        supplementary_bytes, supplementary_count, supplementary_exts = (
            self._supplementary_file_stats(folder_path)
        )
        total_bytes = inventory_bytes + supplementary_bytes
        all_exts = sorted(inventory_exts | supplementary_exts)
        return {
            "folder_path": str(folder_path),
            "num_files": len(files) + supplementary_count,
            "file_size": format_file_size(total_bytes),
            "extensions": ", ".join(all_exts),
        }

    @staticmethod
    def _supplementary_file_stats(folder_path: Path) -> tuple[int, int, set[str]]:
        """
        Return byte total, file count, and extensions for ADC metadata sidecars.

        Args:
            folder_path: Project output directory.

        Returns:
            Tuple of (total bytes, file count, extension set).
        """
        total_bytes = 0
        count = 0
        extensions: set[str] = set()
        for name in (_METADATA_JSON_NAME, _CATALOG_HTML_NAME):
            path = folder_path / name
            if not path.is_file():
                continue
            count += 1
            total_bytes += path.stat().st_size
            if path.suffix:
                extensions.add(path.suffix.lstrip(".").lower())
        return total_bytes, count, extensions

    def _process_files(
        self,
        drpid: int,
        folder_path: Path,
        files: list[dict[str, Any]],
    ) -> tuple[list[str], int, set[str], bool]:
        """
        Download Figshare-hosted inventory files; skip those over 1 GB.

        Returns:
            Tuple of (status_note_lines for >1GB skips only, total_bytes, extensions, skipped_large).
        """
        notes: list[str] = []
        total_bytes = 0
        exts: set[str] = set()
        skipped_large = False

        for file_row in files:
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

            Logger.info("Downloading ADC file: %s", filename)
            _bytes_written, success = download_with_retry(
                lambda url=file_url, path=dest: download_via_url(
                    url,
                    path,
                    timeout_sec=_DOWNLOAD_TIMEOUT_SEC,
                ),
                max_retries=self._download_retries,
                base_delay=self._retry_backoff,
                operation_label=f"ADC download {filename}",
            )
            if not success:
                record_error(drpid, f"Download failed: {filename} - {file_url}")
                continue

            if dest.exists():
                total_bytes += dest.stat().st_size
                Logger.info("Downloaded ADC file: %s", filename)

        return notes, total_bytes, exts, skipped_large

    def _write_aria2_cmd(
        self,
        drpid: int,
        folder_path: Path,
        files: list[dict[str, Any]],
    ) -> None:
        """Export aria2 commands for skipped large files."""
        from collectors.AdcAria2Export import write_drpid_aria2_cmd

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
