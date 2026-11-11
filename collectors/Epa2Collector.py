"""
EPA2 collector for DRP Pipeline.

Collects one EDG Clip and Ship item: a landing-page PDF with Load more and
down arrows expanded, service JSON when the item is a feature service, and
the Hub open-format exports that fit in the download budget.

Run via orchestrator when ``Args.source`` is ``epa2``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collectors.CollectorBase import CollectorBase
from collectors.EpaHubExports import EpaHubExports
from collectors.EpaHubItem import (
    EpaHubItemClient,
    bbox_from_geometry,
    metadata_from_feature,
)
from collectors.UsfsPageDownloader import UsfsPageDownloader
from sourcing.EpaHubCandidateFetcher import item_id_from_source_url, landing_page_url
from utils.Errors import abort_project, record_error, record_warning
from utils.IcpsrGeographicNormalizer import normalize_geographic_metadata
from utils.Logger import Logger

LANDING_PDF_NAME = "landing_page.pdf"


class Epa2Collector(CollectorBase):
    """Collect a Clip and Ship landing page and its downloadable files."""

    _storage_status_mode = "inventory"

    def __init__(
        self,
        *,
        headless: bool = True,
        page_downloader: UsfsPageDownloader | None = None,
        item_client: EpaHubItemClient | None = None,
        exports: EpaHubExports | None = None,
    ) -> None:
        """
        Initialize the collector.

        Args:
            headless: Launch Playwright headless when this collector owns the browser.
            page_downloader: PDF renderer. Created per project when omitted.
            item_client: Hub item client.
            exports: Service JSON and export downloader.
        """
        self._headless = headless
        self._page_downloader = page_downloader
        self._items = item_client or EpaHubItemClient()
        self._exports = exports or EpaHubExports()

    def _collect(self, url: str, drpid: int, record: dict[str, Any]) -> dict[str, Any]:
        """Collect one Clip and Ship item into its project folder."""
        del record
        if not self.validate_url(drpid, url):
            return {}
        item_id = item_id_from_source_url(url)
        if not item_id:
            abort_project(drpid, f"Not an EDG Clip and Ship item URL: {url}")
        feature = self._load_feature(drpid, item_id)
        if feature is None:
            return {}
        folder = self.create_project_folder(drpid)
        if folder is None:
            return {}
        pages, owns_pages = self._open_pages()
        try:
            self._save_landing_pdf(pages, folder, url, drpid)
        finally:
            if owns_pages:
                pages.close()
        notes, planned = self._exports.download_all(folder, feature)
        result = self._result_from_feature(drpid, feature)
        result["folder_path"] = str(folder)
        if notes:
            result["status_notes"] = "\n".join(notes)
        status = self._exports.commit(drpid, folder, planned)
        if status != "collected":
            result["status"] = status
            result["_skipped_large_file"] = True
        self.finalize_folder_stats(result, folder)
        self._note_missing_data(drpid, feature, planned)
        Logger.info("EPA2 collection complete for DRPID %s", drpid)
        return result

    def _load_feature(self, drpid: int, item_id: str) -> dict[str, Any] | None:
        """Fetch the Hub feature, recording an error on failure."""
        try:
            return self._items.fetch_feature(item_id)
        except Exception as exc:
            record_error(drpid, f"Failed to load EDG item {item_id}: {exc}")
            return None

    def _save_landing_pdf(
        self,
        pages: UsfsPageDownloader,
        folder: Path,
        source_url: str,
        drpid: int,
    ) -> None:
        """Print the about/landing page after Load more and down arrows expand."""
        target = landing_page_url(source_url)
        if pages.url_to_pdf(target, folder / LANDING_PDF_NAME, spa_ready=True):
            Logger.info("Saved %s from %s", LANDING_PDF_NAME, target)
            return
        abort_project(drpid, f"Failed to save landing page PDF: {LANDING_PDF_NAME}")

    def _result_from_feature(self, drpid: int, feature: dict[str, Any]) -> dict[str, Any]:
        """Build the Storage result, including geographic coverage."""
        result = metadata_from_feature(feature)
        box = bbox_from_geometry(feature.get("geometry"))
        if box is None:
            return result
        geo = normalize_geographic_metadata(bounding_box=box)
        if geo.geographic_coverage:
            result["geographic_coverage"] = geo.geographic_coverage
        for warning in geo.warnings:
            record_warning(drpid, warning)
        return result

    def _note_missing_data(
        self,
        drpid: int,
        feature: dict[str, Any],
        planned: list[Any],
    ) -> None:
        """Record an error when a data item saved no downloadable file."""
        properties = feature.get("properties")
        props = properties if isinstance(properties, dict) else {}
        if str(props.get("type") or "").strip().casefold() == "hub page":
            return
        saved = [item for item in planned if not getattr(item, "access_error", None)]
        if saved:
            return
        record_error(drpid, "No Clip and Ship data file was downloaded")

    def _open_pages(self) -> tuple[UsfsPageDownloader, bool]:
        """Return a page downloader and whether this collector must close it."""
        if self._page_downloader is not None:
            return self._page_downloader, False
        return UsfsPageDownloader(headless=self._headless), True
