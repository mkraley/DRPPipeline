"""
FERC collector for DRP Pipeline.

Catalog datasets save a landing page, table, details, and dictionary.
An Electric Quarterly Report URL with ``start`` and ``end`` quarters saves
that year range of CSV zips instead.

For each sourced dataset landing page, saves:

* ``landing_page.pdf``
* ``dataset.csv``
* ``details.json`` when the details endpoint returns a body
* ``dictionary.csv`` from the embedded page dictionary when present,
  otherwise from the shorter API dictionary

Keywords, time range, data types, and geographic coverage are filled with
the same inference the interactive collector uses for Fill metadata.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from collectors.CollectorBase import CollectorBase
from collectors.FercCollectedFiles import (
    DATASET_NAME,
    DETAILS_NAME,
    DICTIONARY_NAME,
    LANDING_PDF_NAME,
    write_dataset_csv,
    write_details_json,
    write_dictionary_csv,
)
from collectors.FercDatasetClient import FercDatasetClient
from collectors.FercKeywords import apply_ferc_keywords
from collectors.FercLandingDictionary import fetch_landing_html, parse_embedded_dictionary
from collectors.UsfsPageDownloader import UsfsPageDownloader
from sourcing.FercCandidateFetcher import canonical_dataset_url, rows_from_assets
from sourcing.FercCatalogClient import FercCatalogClient
from utils.Args import Args
from utils.Errors import abort_project
from utils.Logger import Logger

HtmlFetcher = Callable[[str], str]


class FercCollector(CollectorBase):
    """Collect a FERC dataset landing page, table, details, and dictionary."""

    def __init__(
        self,
        *,
        headless: bool = True,
        page_downloader: UsfsPageDownloader | None = None,
        dataset_client: FercDatasetClient | None = None,
        catalog_client: FercCatalogClient | None = None,
        html_fetcher: HtmlFetcher | None = None,
    ) -> None:
        """
        Initialize the collector.

        Args:
            headless: Launch Playwright headless when this collector owns the browser.
            page_downloader: PDF renderer. Created per project when omitted.
            dataset_client: Details, dictionary, and data client.
            catalog_client: Catalog client used to map landing URLs to dataset ids.
            html_fetcher: Landing-page HTML loader. Defaults to ``fetch_landing_html``.
        """
        self._headless = headless
        self._page_downloader = page_downloader
        self._datasets = dataset_client or FercDatasetClient()
        self._catalog = catalog_client or FercCatalogClient()
        self._html_fetcher = html_fetcher or fetch_landing_html
        self._ids_by_url: dict[str, int] | None = None

    def _collect(self, url: str, drpid: int, record: dict[str, Any]) -> dict[str, Any]:
        """Collect one dataset into its project folder."""
        if not self.validate_url(drpid, url):
            return {}
        eqr_result = self._collect_eqr(url, drpid, record)
        if eqr_result is not None:
            return eqr_result
        dataset_id = self._dataset_id(url)
        if dataset_id is None:
            abort_project(drpid, f"FERC catalog has no dataset for {url}")
        folder = self.create_project_folder(drpid)
        if folder is None:
            return {}
        pages, owns_pages = self._open_pages()
        try:
            self._save_landing_pdf(pages, folder, url, drpid)
            self._save_details(folder, dataset_id)
            self._save_dictionary(folder, url, dataset_id)
            written = write_dataset_csv(
                folder / DATASET_NAME,
                self._datasets,
                dataset_id,
                pause_sec=_request_delay(),
            )
            Logger.info("FERC dataset %s: wrote %s row(s)", dataset_id, written)
        finally:
            if owns_pages:
                pages.close()
        result: dict[str, Any] = {"folder_path": str(folder)}
        self.finalize_folder_stats(result, folder)
        self._apply_inferred_metadata(result, record, folder, drpid)
        return result

    def _collect_eqr(self, url: str, drpid: int, record: dict[str, Any]) -> dict[str, Any] | None:
        """Collect an EQR year-range project, or return None for a catalog dataset."""
        from collectors.EqrCollector import EqrCollector
        from collectors.EqrProjectRange import range_from_source_url

        if range_from_source_url(url) is None:
            return None
        return EqrCollector(page_downloader=self._page_downloader).collect(url, drpid, record)

    def _apply_inferred_metadata(
        self,
        result: dict[str, Any],
        record: dict[str, Any],
        folder: Path,
        drpid: int,
    ) -> None:
        """Fill metadata fields from the title, summary, and files just saved."""
        from interactive_collector.metadata_inference import infer_project_metadata

        try:
            fields, notes = infer_project_metadata(
                str(record.get("title") or ""),
                str(record.get("summary") or ""),
                folder,
            )
        except Exception as exc:
            Logger.warning("FERC metadata inference failed for DRPID %s: %s", drpid, exc)
            return
        for note in notes:
            Logger.warning("DRPID %s: %s", drpid, note)
        apply_ferc_keywords(
            fields,
            str(record.get("title") or ""),
            str(record.get("summary") or ""),
        )
        result.update(fields)
        if fields:
            Logger.info("Inferred metadata for DRPID %s: %s", drpid, fields)

    def _dataset_id(self, url: str) -> int | None:
        """Return the catalog id for a landing-page URL."""
        canonical = canonical_dataset_url(url)
        if canonical is None:
            return None
        return self._id_index().get(canonical)

    def _id_index(self) -> dict[str, int]:
        """Load landing URL to dataset id once per collector instance."""
        if self._ids_by_url is None:
            rows = rows_from_assets(self._catalog.fetch_data_assets())
            self._ids_by_url = {row["url"]: int(row["record_id"]) for row in rows}
            self._catalog.close()
        return self._ids_by_url

    def _open_pages(self) -> tuple[UsfsPageDownloader, bool]:
        """Return a PDF renderer and whether this call owns it."""
        if self._page_downloader is not None:
            return self._page_downloader, False
        return UsfsPageDownloader(headless=self._headless), True

    def _save_landing_pdf(
        self,
        pages: UsfsPageDownloader,
        folder: Path,
        url: str,
        drpid: int,
    ) -> None:
        """Print the landing page to ``landing_page.pdf``."""
        if not pages.url_to_pdf(url, folder / LANDING_PDF_NAME):
            abort_project(drpid, f"Failed to save landing page PDF: {url}")
        Logger.info("Saved %s", LANDING_PDF_NAME)

    def _save_details(self, folder: Path, dataset_id: int) -> None:
        """Save details JSON when the endpoint returns a body."""
        details = self._datasets.fetch_details(dataset_id)
        if details is None:
            Logger.info("FERC dataset %s has no details file", dataset_id)
            return
        write_details_json(folder / DETAILS_NAME, details)
        Logger.info("Saved %s", DETAILS_NAME)

    def _save_dictionary(self, folder: Path, url: str, dataset_id: int) -> None:
        """Save the embedded dictionary, or the API dictionary when that is all there is."""
        rows = self._embedded_dictionary(url)
        if rows is None:
            rows = self._datasets.fetch_dictionary(dataset_id)
        if not rows:
            Logger.info("FERC dataset %s has no dictionary", dataset_id)
            return
        write_dictionary_csv(folder / DICTIONARY_NAME, rows)
        Logger.info("Saved %s (%s row(s))", DICTIONARY_NAME, len(rows))

    def _embedded_dictionary(self, url: str) -> list[dict[str, Any]] | None:
        """Read the long-form dictionary from the landing page, if it is embedded."""
        try:
            html = self._html_fetcher(url)
        except Exception as exc:
            Logger.warning("FERC landing dictionary unavailable for %s: %s", url, exc)
            return None
        return parse_embedded_dictionary(html)


def _request_delay() -> float:
    """Return the pause between data-API pages."""
    return float(getattr(Args, "ferc_request_delay", 0.1) or 0.0)
