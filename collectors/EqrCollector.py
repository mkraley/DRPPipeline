"""Collect one year-range of EQR CSV quarterly zips."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

import requests

from collectors.BudgetedDownload import BudgetedDownload
from collectors.CollectorBase import CollectorBase
from collectors.EqrDictionary import DICTIONARY_NAME, dictionary_url_from_html
from collectors.EqrProjectRange import EXPLAIN_URL, EqrProjectRange, range_from_source_url
from collectors.EqrZipCatalog import EqrZipCatalog
from collectors.EqrZipLink import EqrZipLink, links_for_range
from collectors.EqrZipSize import zip_content_length
from collectors.FercCollectedFiles import LANDING_PDF_NAME
from collectors.FercKeywords import keywords_for_ferc
from collectors.PlannedFile import PlannedFile
from utils.Errors import abort_project
from utils.Logger import Logger
from utils.download_with_progress import download_via_url
from utils.file_utils import format_file_size
from utils.url_utils import BROWSER_HEADERS, requests_verify

FileDownload = Callable[[str, Path], tuple[int, bool]]
LinkSource = Callable[[], list[EqrZipLink]]


class EqrCollector:
    """Save the CSV zips for one EQR project, stopping at the 1 GiB budget."""

    def __init__(
        self,
        *,
        page_downloader: Any = None,
        link_source: LinkSource | None = None,
        download_file: FileDownload | None = None,
        explain_html: str | None = None,
    ) -> None:
        """
        Initialize the collector.

        Args:
            page_downloader: PDF renderer. Created when omitted.
            link_source: Quarterly CSV link loader. Defaults to the live viewer.
            download_file: Bytes downloader. Defaults to ``download_via_url``.
            explain_html: Explanation-page HTML. Fetched when omitted.
        """
        self._page_downloader = page_downloader
        self._link_source = link_source or EqrZipCatalog().list_links
        self._download_file = download_file or _download_via_url
        self._explain_html = explain_html

    def collect(self, url: str, drpid: int, record: dict[str, Any]) -> dict[str, Any]:
        """
        Collect the CSV zips for the span encoded in ``url``.

        Args:
            url: Viewer URL with ``start`` and ``end`` quarter parameters.
            drpid: Project DRPID.
            record: Storage row, used for the title when it is already set.

        Returns:
            Storage fields, including ``collected - large`` when the span exceeds 1 GiB.
        """
        span = range_from_source_url(url)
        if span is None:
            abort_project(drpid, f"Not an EQR project URL: {url}")
        folder = CollectorBase.create_project_folder(drpid, recreate=False)
        if folder is None:
            return {}
        selected = self._selected_links(drpid, span)
        self._save_sidecars(drpid, folder)
        planned = [PlannedFile(link.name, link.url, link.size_bytes) for link in selected]
        notes = self._download_planned(drpid, folder, planned)
        status = BudgetedDownload().commit_inventory(drpid, folder, planned)
        return _result(folder, record, span, planned, notes, status)

    def _selected_links(self, drpid: int, span: EqrProjectRange) -> list[EqrZipLink]:
        """Return sized CSV zips inside ``span``."""
        selected = links_for_range(self._link_source(), span)
        if not selected:
            abort_project(drpid, f"No CSV quarterly zips for {span.label()}")
        try:
            return [_with_size(link) for link in selected]
        except RuntimeError as exc:
            abort_project(drpid, str(exc))

    def _save_sidecars(self, drpid: int, folder: Path) -> None:
        """Save the explanation PDF and the V3.5 data dictionary."""
        pages, owns_pages = self._pages()
        try:
            _save_pdf(pages, drpid, folder)
            _save_dictionary(folder, self._explain_html, self._download_file, drpid)
        finally:
            if owns_pages:
                pages.close()

    def _pages(self) -> tuple[Any, bool]:
        """Return a PDF renderer and whether this call owns it."""
        if self._page_downloader is not None:
            return self._page_downloader, False
        from collectors.UsfsPageDownloader import UsfsPageDownloader

        return UsfsPageDownloader(headless=True), True

    def _download_planned(self, drpid: int, folder: Path, planned: list[PlannedFile]) -> list[str]:
        """Download zips until the shared 1 GiB budget is exhausted."""

        def download_one(item: PlannedFile, dest: Path) -> bool:
            Logger.info("Downloading %s (%s)", item.filename(), format_file_size(item.size_bytes or 0))
            _written, success = self._download_file(item.source_url, dest)
            return bool(success and dest.is_file())

        outcome = BudgetedDownload().download_until_budget(drpid, folder, planned, download_one)
        return outcome.notes


def _download_via_url(url: str, dest: Path) -> tuple[int, bool]:
    """Stream one zip or dictionary to ``dest``."""
    return download_via_url(url, dest)


def _with_size(link: EqrZipLink) -> EqrZipLink:
    """Fill a missing Content-Length."""
    if link.size_bytes is not None:
        return link
    return link.with_size(zip_content_length(link.url))


def _save_pdf(pages: Any, drpid: int, folder: Path) -> None:
    """Print the EQR explanation page when the PDF is not already saved."""
    dest = folder / LANDING_PDF_NAME
    if dest.is_file() and dest.stat().st_size > 0:
        return
    if not pages.url_to_pdf(EXPLAIN_URL, dest):
        abort_project(drpid, f"Failed to save landing page PDF: {EXPLAIN_URL}")


def _save_dictionary(
    folder: Path,
    html: str | None,
    download_file: FileDownload,
    drpid: int,
) -> None:
    """Save the V3.5 dictionary PDF when it is not already saved."""
    dest = folder / DICTIONARY_NAME
    if dest.is_file() and dest.stat().st_size > 0:
        return
    page_html = html if html is not None else _fetch_explain_html()
    url = dictionary_url_from_html(page_html)
    _written, success = download_file(url, dest)
    if not success or not dest.is_file():
        abort_project(drpid, f"Failed to save EQR data dictionary: {url}")


def _fetch_explain_html() -> str:
    """Download the FERC EQR explanation page."""
    response = requests.get(
        EXPLAIN_URL,
        timeout=60,
        verify=requests_verify(),
        headers=BROWSER_HEADERS,
    )
    response.raise_for_status()
    return response.text


def _result(
    folder: Path,
    record: dict[str, Any],
    span: EqrProjectRange,
    planned: list[PlannedFile],
    notes: list[str],
    status: str,
) -> dict[str, Any]:
    """Build the Storage update for one collected span."""
    title = str(record.get("title") or span.title())
    sidecars = sum(1 for name in (LANDING_PDF_NAME, DICTIONARY_NAME) if (folder / name).is_file())
    fields: dict[str, Any] = {
        "folder_path": str(folder),
        "title": title,
        "summary": str(record.get("summary") or span.summary()),
        "keywords": keywords_for_ferc(title),
        "time_start": span.time_start(),
        "time_end": span.time_end(),
        "geographic_coverage": "United States",
        "data_types": "Administrative records data",
        "num_files": len(planned) + sidecars,
        "file_size": format_file_size(sum(item.size_bytes or 0 for item in planned)),
        "extensions": "pdf, zip",
        "status": status,
        "download_date": date.today().isoformat(),
    }
    if notes:
        fields["status_notes"] = "\n".join(notes)
    return fields
