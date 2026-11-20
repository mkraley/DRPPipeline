"""
AQS collector for DRP Pipeline.

Downloads the yearly zips for one AirData column and copies
``AirData FileFormats.pdf`` from the AQS output folder into the project.
The site project also saves file_list.csv, and a column that links the PM2.5
advisory saves that PDF. Downloads stop at the shared 1 GiB budget.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from collectors.BudgetedDownload import BudgetedDownload
from collectors.CollectorBase import CollectorBase
from collectors.PlannedFile import PlannedFile
from sourcing.AqsDownloadClient import AqsDownloadClient, file_url
from sourcing.AqsFile import AqsFile
from sourcing.AqsPageParser import AqsPageParser
from sourcing.AqsSeries import FORMATS_PDF_NAME, AqsSeries
from utils.Args import Args
from utils.Errors import abort_project, record_error
from utils.Logger import Logger
from utils.download_with_progress import download_via_url
from utils.inventory_status import STATUS_COLLECTED

FileDownload = Callable[[str, Path], tuple[int, bool]]
LengthProbe = Callable[[str], int | None]


class AqsCollector(CollectorBase):
    """Collect one pre-generated AirData column into its project folder."""

    _storage_status_mode = "inventory"

    def __init__(
        self,
        *,
        parser: AqsPageParser | None = None,
        client: AqsDownloadClient | None = None,
        download_file: FileDownload | None = None,
        content_length: LengthProbe | None = None,
    ) -> None:
        """
        Initialize the collector.

        Args:
            parser: Download-page parser (created when omitted).
            client: Page and file-size client (created when omitted).
            download_file: Bytes downloader. Defaults to ``download_via_url``.
            content_length: Content-Length probe. Defaults to the client.
        """
        self._parser = parser or AqsPageParser()
        self._client = client or AqsDownloadClient()
        self._download_file = download_file or download_via_url
        self._content_length = content_length or self._client.content_length
        self._series: list[AqsSeries] | None = None

    def _collect(self, url: str, drpid: int, record: dict[str, Any]) -> dict[str, Any]:
        """Download one column into its project folder."""
        del record
        if not self.validate_url(drpid, url):
            return {}
        series = self._find_series(drpid, url)
        folder = self.create_project_folder(drpid, recreate=False)
        if folder is None:
            return {}
        planned = [self._planned_file(item) for item in _collect_order(series)]
        format_pdf = self._copy_format_pdf(drpid, folder)
        if format_pdf is not None:
            planned.insert(0, format_pdf)
        notes = self._download(drpid, folder, planned)
        return self._result(drpid, folder, series, planned, notes)

    def _find_series(self, drpid: int, url: str) -> AqsSeries:
        """Return the column named by the project URL fragment."""
        series_id = urlparse(url).fragment.strip()
        for item in self._load_series():
            if item.series_id == series_id:
                return item
        abort_project(drpid, f"AirData download page has no column {series_id!r}")

    def _load_series(self) -> list[AqsSeries]:
        """Parse the download page once per collector."""
        if self._series is None:
            self._series = self._parser.parse_html(self._client.fetch_html())
        return self._series

    def _copy_format_pdf(self, drpid: int, folder: Path) -> PlannedFile | None:
        """Copy the shared format PDF into this project folder."""
        source = Path(Args.base_output_dir) / FORMATS_PDF_NAME
        dest = folder / FORMATS_PDF_NAME
        if not source.is_file():
            record_error(drpid, f"Format PDF is missing: {source}")
            return None
        if source.resolve() != dest.resolve():
            shutil.copy2(source, dest)
        return PlannedFile(FORMATS_PDF_NAME, str(source), dest.stat().st_size)

    def _planned_file(self, item: AqsFile) -> PlannedFile:
        """Build a budgeted download for one AirData file."""
        url = file_url(item.filename)
        return PlannedFile(item.filename, url, self._size_bytes(item, url))

    def _size_bytes(self, item: AqsFile, url: str) -> int:
        """Return a known byte size so the budget can download the file."""
        probed = self._content_length(url)
        if isinstance(probed, int) and probed >= 0:
            return probed
        if item.size_kb > 0:
            return item.size_kb * 1024
        return 1

    def _download(self, drpid: int, folder: Path, planned: list[PlannedFile]) -> list[str]:
        """Download files until the 1 GiB budget is exhausted."""

        def download_one(item: PlannedFile, dest: Path) -> bool:
            Logger.info("Downloading %s", item.filename())
            _written, success = self._download_file(item.source_url, dest)
            if success and dest.is_file():
                return True
            record_error(drpid, f"Download failed: {item.filename()} - {item.source_url}")
            return False

        outcome = BudgetedDownload().download_until_budget(drpid, folder, planned, download_one)
        return outcome.notes

    def _result(
        self,
        drpid: int,
        folder: Path,
        series: AqsSeries,
        planned: list[PlannedFile],
        notes: list[str],
    ) -> dict[str, Any]:
        """Build the Storage update for one collected column."""
        status = BudgetedDownload().commit_inventory(drpid, folder, planned)
        result: dict[str, Any] = series.metadata_fields()
        result["folder_path"] = str(folder)
        if notes:
            result["status_notes"] = "\n".join(notes)
        self.finalize_folder_stats(result, folder, planned)
        if status != STATUS_COLLECTED:
            result["status"] = status
        result["_skipped_large_file"] = status != STATUS_COLLECTED
        return result


def _collect_order(series: AqsSeries) -> tuple[AqsFile, ...]:
    """Save small extras before the yearly zips."""
    packaged = series.packaged_files()
    extras = [item for item in packaged if item.kind != "data"]
    data = [item for item in packaged if item.kind == "data"]
    return tuple(extras + data)
