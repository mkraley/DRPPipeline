"""
Sourcing module for DRP Pipeline.

Obtains candidate source URLs from parameterized sources (e.g. DRP Data_Inventories
spreadsheet), performs duplicate prevention and availability checks, and creates
storage records with generated IDs for each new candidate.
"""

import csv
import io
from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from utils.Args import Args
from utils.Logger import Logger
from utils.sheet_url_utils import parse_spreadsheet_url

from .SourceConfig import SourceConfig

if TYPE_CHECKING:
    from storage.StorageProtocol import StorageProtocol


class Sourcing:
    """
    Orchestrates sourcing of candidate URLs: fetch from configured sources,
    check duplicates and availability, create storage records.
    """

    def __init__(self, storage: "StorageProtocol") -> None:
        """
        Initialize Sourcing with a storage backend.

        Args:
            storage: Storage implementation for creating and querying records.
        """
        self._storage = storage

    def run(self, sources: list[SourceConfig]) -> None:
        """
        Process all configured sources: obtain candidate URLs, then for each
        candidate run duplicate check, availability check, and create storage
        record when appropriate.

        Args:
            sources: List of source configs (e.g. spreadsheet/tab + filter).
        """
        ...

    def get_candidate_urls(self, source: SourceConfig) -> list[str]:
        """
        Obtain candidate source URLs from a parameterized source.

        Reads from a Google Sheets tab (spreadsheet/tab from Args or source override),
        filters rows where configured columns are empty (e.g. Claimed, Download Location),
        and returns non-empty URL values.

        Args:
            source: Configuration specifying spreadsheet, tab, and optional filter.

        Returns:
            List of candidate URLs to process.
        """
        spreadsheet_url = source.spreadsheet or Args.sourcing_spreadsheet_url
        sheet_id, gid = parse_spreadsheet_url(spreadsheet_url)
        if source.tab:
            gid = source.tab
        csv_text = self._fetch_sheet_csv(sheet_id, gid)
        url_column = Args.sourcing_url_column
        empty_columns = Args.sourcing_filter_empty_columns
        return self._extract_urls_from_csv(csv_text, url_column, empty_columns)

    def _fetch_sheet_csv(self, sheet_id: str, gid: str) -> str:
        """
        Fetch a Google Sheets tab as CSV via the public export URL.

        Args:
            sheet_id: Spreadsheet ID from the sheet URL.
            gid: Sheet/tab gid.

        Returns:
            CSV body as string (UTF-8-sig).

        Raises:
            URLError: On network or HTTP errors.
        """
        export_url = (
            f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        )
        req = Request(export_url, headers={"User-Agent": "DRPPipeline/1.0"})
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8-sig")
        except (HTTPError, URLError) as e:
            Logger.error(f"Failed to fetch spreadsheet CSV: {e}")
            raise

    def _row_passes_filter(
        self, row: dict[str, str], empty_columns: list[str]
    ) -> bool:
        """
        Return True if all configured columns are empty (after strip).

        Used to filter rows where e.g. Claimed and Download Location are empty.

        Args:
            row: Dict mapping column names to cell values.
            empty_columns: Column names that must be empty.

        Returns:
            True if every listed column is empty or missing.
        """
        for col in empty_columns:
            val = row.get(col, "")
            if isinstance(val, str) and val.strip():
                return False
        return True

    def _extract_urls_from_csv(
        self, csv_text: str, url_column: str, empty_columns: list[str]
    ) -> list[str]:
        """
        Parse CSV, filter rows, and collect non-empty URL values.

        Handles missing columns gracefully (logs warning, skips or returns []).
        """
        reader = csv.DictReader(io.StringIO(csv_text))
        fieldnames = reader.fieldnames or []
        if url_column not in fieldnames:
            Logger.warning(
                f"CSV missing URL column '{url_column}'. "
                f"Available columns: {fieldnames}"
            )
            return []
        missing = [c for c in empty_columns if c not in fieldnames]
        if missing:
            Logger.warning(
                f"CSV missing filter columns {missing}; excluding them from filter. "
                f"Available: {fieldnames}"
            )
            empty_columns = [c for c in empty_columns if c in fieldnames]
        urls: list[str] = []
        for row in reader:
            if not self._row_passes_filter(row, empty_columns):
                continue
            raw = row.get(url_column, "")
            url = (raw or "").strip()
            if url:
                urls.append(url)
        return urls

    def process_candidate(self, url: str) -> bool:
        """
        Process a single candidate URL: duplicate check, availability check,
        then create storage record and generate ID if both pass.

        If the URL is already in the repository, no further processing.
        If the source URL is not available, no further processing.

        Args:
            url: Candidate source URL.

        Returns:
            True if a storage record was created; False if skipped (duplicate
            or unavailable).
        """
        return False

    def is_duplicate(self, url: str) -> bool:
        """
        Check whether the URL already exists in the repository.

        Used for duplicate prevention before creating a new record.

        Args:
            url: Candidate source URL.

        Returns:
            True if URL is already stored; False otherwise.
        """
        return False

    def is_source_available(self, url: str) -> bool:
        """
        Check whether the source URL is reachable/available.

        If not available, we cannot proceed with collection for this URL.

        Args:
            url: Candidate source URL.

        Returns:
            True if URL is available; False otherwise.
        """
        return True

    def create_storage_record_and_id(self, url: str) -> int:
        """
        Create a storage record for the URL and return its generated ID.

        Args:
            url: Source URL for the new record.

        Returns:
            The DRPID of the created record.
        """
        return self._storage.create_record(url)
