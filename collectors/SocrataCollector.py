"""
Socrata Collector for DRP Pipeline.

Collects data from Socrata-hosted pages (e.g., data.cdc.gov):
- Pre-processes HTML (expands "read more" links)
- Harvests metadata (rows, columns, description, keywords)
- Converts HTML to PDF
- Downloads datasets
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from collectors.CollectorBase import CollectorBase
from collectors.PlaywrightSession import PlaywrightSession
from collectors.SocrataDatasetDownloader import SocrataDatasetDownloader
from collectors.SocrataMetadataExtractor import SocrataMetadataExtractor
from collectors.SocrataPageProcessor import SocrataPageProcessor
from collectors.collector_url import validate_and_access_url
from utils.Errors import record_error
from utils.file_utils import folder_extensions_and_size, sanitize_filename
from utils.Logger import Logger


class SocrataCollector(CollectorBase):
    """
    Collector for Socrata-hosted data pages.

    Handles collection of data from Socrata sites including URL validation,
    PDF generation, dataset download, and metadata extraction.
    """

    def __init__(self, headless: bool = True) -> None:
        """
        Initialize SocrataCollector.

        Args:
            headless: If False, run browser in visible mode for debugging.
        """
        self._headless = headless
        self._session = PlaywrightSession(
            headless=headless,
            slow_mo=500 if not headless else 0,
        )
        self._drpid = 0
        self._result: dict[str, Any] = {}

    @property
    def _page(self):
        """Default Playwright page (used by helper classes and tests)."""
        return self._session.page

    def _collect(
        self,
        url: str,
        drpid: int,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Collect data from a Socrata URL.

        Args:
            url: Source URL to collect from.
            drpid: DRPID for the record.
            record: Full Storage record (unused).

        Returns:
            Flat dict with Storage field names for merge.
        """
        self._drpid = drpid
        self._result = {}

        if not validate_and_access_url(drpid, url):
            return self._result

        folder_path = self.create_project_folder(drpid)
        if folder_path is None:
            return self._result
        self._result["folder_path"] = str(folder_path)

        try:
            if not self._init_browser_and_load_page(url):
                return self._result
            self._process_and_generate_pdf(folder_path)
            self._download_dataset_and_extract_metadata(folder_path)
        except Exception as exc:
            record_error(drpid, f"Collection error: {exc}")
        finally:
            self._cleanup_browser()

        fp = self._result.get("folder_path")
        if fp:
            folder = Path(fp)
            if folder.is_dir():
                _exts, _total_bytes, num_files = folder_extensions_and_size(folder)
                self._result["num_files"] = num_files

        return self._result

    def _init_browser_and_load_page(self, url: str) -> bool:
        """Initialize browser and load the source page."""
        if not self._init_browser():
            record_error(self._drpid, "Failed to initialize browser")
            return False
        try:
            assert self._session.page is not None
            self._session.page.goto(url, wait_until="domcontentloaded", timeout=120000)
            self._session.page.wait_for_timeout(500)
            return True
        except Exception as exc:
            record_error(self._drpid, f"Failed to load page: {exc}")
            return False

    def _process_and_generate_pdf(self, folder_path: Path) -> None:
        """Process page and generate PDF using the page title as filename."""
        page_processor = SocrataPageProcessor(self)
        try:
            page_title = self._session.page.title() if self._session.page else ""
            pdf_filename = (
                sanitize_filename(page_title) + ".pdf" if page_title else "page.pdf"
            )
        except Exception:
            pdf_filename = "page.pdf"
        page_processor.generate_pdf(folder_path / pdf_filename)

    def _download_dataset_and_extract_metadata(self, folder_path: Path) -> None:
        """Download dataset and extract metadata."""
        SocrataDatasetDownloader(self).download(folder_path)
        SocrataMetadataExtractor(self).extract_all_metadata()

    def _init_browser(self) -> bool:
        """Initialize Playwright browser and page."""
        return self._session.start()

    def _cleanup_browser(self) -> None:
        """Clean up browser resources."""
        self._session.close()
