"""
AQS sourcing module for DRP Pipeline.

Reads the EPA AirData pre-generated download page and creates one ``sourced``
project per table column. Run via orchestrator when ``Args.source`` is ``aqs``::

    python main.py source --source aqs
"""

from __future__ import annotations

from duplicate_checking import DuplicateChecker
from sourcing.AqsDownloadClient import AqsDownloadClient
from sourcing.AqsPageParser import AqsPageParser
from sourcing.AqsSeries import AqsSeries
from sourcing.SourcingBase import SourcingBase
from storage import Storage
from utils.Args import Args
from utils.Logger import Logger

_LABEL = "AQS"


class AqsSourcing(SourcingBase):
    """Source AirData pre-generated columns into Storage."""

    def __init__(
        self,
        *,
        parser: AqsPageParser | None = None,
        client: AqsDownloadClient | None = None,
    ) -> None:
        """
        Initialize the sourcing module.

        Args:
            parser: Download-page parser (created when omitted).
            client: Page client (created when omitted).
        """
        self._parser = parser or AqsPageParser()
        self._client = client or AqsDownloadClient()

    def run(self, drpid: int) -> None:
        """
        Insert one project per download-page column.

        ``Args.num_rows`` limits how many pending columns are inserted per run.

        Args:
            drpid: Use -1 (orchestrator convention for batch sourcing modules).
        """
        self.ensure_batch_drpid(drpid, self.__class__.__name__)
        limit = Args.num_rows
        Logger.info("%s sourcing: reading the AirData download page (limit=%s)", _LABEL, limit)
        series = self._parser.parse_html(self._client.fetch_html())
        self._insert_pending(series, limit)

    def _insert_pending(self, series: list[AqsSeries], limit: int | None) -> None:
        """Insert pending columns up to the batch limit."""
        pending = self._pending(series)
        refreshed = self._refresh_existing(series)
        batch = pending[:limit] if limit is not None else pending
        checker = DuplicateChecker()
        inserted, skipped, failed, assigned = self._insert_batch(batch, checker)
        Logger.info(
            "%s sourcing complete: %s column(s) on the page, %s refreshed, "
            "%s inserted%s, %s failed, %s duplicate(s) skipped, "
            "%s pending for next batch",
            _LABEL,
            len(series),
            refreshed,
            inserted,
            self.format_id_range(assigned),
            failed,
            skipped,
            len(pending) - len(batch),
        )

    def _insert_batch(
        self,
        batch: list[AqsSeries],
        checker: DuplicateChecker,
    ) -> tuple[int, int, int, list[int]]:
        """Insert each pending series that is not already stored."""
        inserted = 0
        skipped = 0
        failed = 0
        assigned: list[int] = []
        for index, item in enumerate(batch, 1):
            outcome, new_id = self._insert_one(item, checker)
            inserted += outcome == "inserted"
            skipped += outcome == "duplicate"
            failed += outcome == "failed"
            if new_id is not None:
                assigned.append(new_id)
            if index <= 20 or index == len(batch):
                Logger.info("%s sourcing progress: %s/%s", _LABEL, index, len(batch))
        return inserted, skipped, failed, assigned

    def _insert_one(
        self,
        item: AqsSeries,
        checker: DuplicateChecker,
    ) -> tuple[str, int | None]:
        """Insert one series and return the outcome and new DRPID."""
        source_url = item.source_url()
        try:
            if self.is_duplicate_in_storage(source_url, checker):
                return "duplicate", None
            new_drpid = Storage.create_record(source_url)
            Storage.update_record(new_drpid, item.storage_fields())
        except Exception as exc:
            Logger.error("%s record %s failed: %s", _LABEL, source_url, exc)
            return "failed", None
        Logger.info("%s sourced %s", _LABEL, item.title())
        return "inserted", new_drpid

    def _pending(self, series: list[AqsSeries]) -> list[AqsSeries]:
        """Return series whose project URLs are not yet stored."""
        stored = set(Storage.list_source_urls())
        return [item for item in series if item.source_url() not in stored]

    def _refresh_existing(self, series: list[AqsSeries]) -> int:
        """Rewrite titles and summaries for columns already in Storage."""
        refreshed = 0
        for item in series:
            drpid = Storage.drpid_for_source_url(item.source_url())
            if drpid is None:
                continue
            Storage.update_record(drpid, item.metadata_fields())
            refreshed += 1
            Logger.info("%s refreshed %s", _LABEL, item.title())
        return refreshed
