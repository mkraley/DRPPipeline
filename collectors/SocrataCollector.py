"""
Socrata Collector for DRP Pipeline.

Collects data from Socrata-hosted pages (e.g., data.cdc.gov):
- Pre-processes HTML (expands "read more" links)
- Harvests metadata (rows, columns, description, keywords)
- Converts HTML to PDF
- Downloads datasets
"""

from contextlib import suppress
from pathlib import Path
from typing import Optional, Dict, Any

from playwright.sync_api import sync_playwright, Page, Browser, Playwright

from storage import Storage
from utils.Logger import Logger
from utils.Logging import record_fatal_error
from utils.Args import Args
from utils.url_utils import is_valid_url, access_url
from utils.file_utils import sanitize_filename, create_output_folder
from collectors.SocrataPageProcessor import SocrataPageProcessor
from collectors.SocrataMetadataExtractor import SocrataMetadataExtractor
from collectors.SocrataDatasetDownloader import SocrataDatasetDownloader

# Storage column names the collector may write (used when transferring result to Storage)
_STORAGE_FIELDS = frozenset({
    "folder_path", "title", "agency", "office", "summary", "keywords",
    "time_start", "time_end", "data_types", "download_date", "collection_notes",
    "file_size", "status", "status_notes", "warnings", "errors",
})


class SocrataCollector:
    """
    Collector for Socrata-hosted data pages.
    
    Handles collection of data from Socrata sites including:
    - URL validation and access
    - PDF generation from HTML pages
    - Dataset download
    - Metadata extraction
    """
    
    def __init__(self, headless: bool = True) -> None:
        """
        Initialize SocrataCollector.
        
        Args:
            headless: If False, run browser in visible mode for debugging
        """
        self._headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._result: Optional[Dict[str, Any]] = None
    
    def run(self, drpid: int) -> None:
        """
        Run the collectors module for a single project (ModuleProtocol interface).
        
        Gets project record from Storage, calls collect() with source_url,
        and updates Storage with collection results.
        
        Args:
            drpid: The DRPID of the project to process.
        """
        # Get project record from Storage
        record = Storage.get(drpid)
        if record is None:
            record_fatal_error(
                drpid,
                f"Project record not found for DRPID: {drpid}",
                update_storage=False,
            )
            return

        # Validate source_url exists
        source_url = record.get("source_url")
        if not source_url:
            record_fatal_error(
                drpid,
                f"Project record missing source_url for DRPID: {drpid}",
            )
            return

        try:
            # Call collect() method
            result = self.collect(source_url, drpid)

            # Transfer result dict to Storage
            self._update_storage_from_result(drpid, result)

        except Exception as e:
            record_fatal_error(
                drpid,
                f"Exception during collection for DRPID {drpid}: {str(e)}",
            )
    
    def collect(self, url: str, drpid: int) -> Dict[str, Any]:
        """
        Collect data from a Socrata URL.
        
        Main entry point for collection. Performs all collection steps:
        1. Validates and accesses URL
        2. Creates output folder (named based on DRPID)
        3. Generates PDF (with original page title, sanitized)
        4. Downloads dataset (with original filename, sanitized)
        5. Extracts metadata
        
        Args:
            url: Source URL to collect from
            drpid: DRPID for the record
            
        Returns:
            Flat dict with Storage field names: folder_path, title, summary,
            keywords, collection_notes, file_size, download_date, status, etc.
            Only non-None entries are transferred to Storage.
        """
        # Flat result dict using Storage field names; only set keys we have values for
        self._result = {}
        
        # Validate and access URL
        if not self._validate_and_access_url(url):
            return self._result
        
        # Create output folder (named based on DRPID)
        base_output_dir = Path(Args.base_output_dir)
        folder_path = create_output_folder(base_output_dir, drpid)
        if not folder_path:
            error_msg = "Failed to create output folder"
            self._append_result_note(error_msg)
            Logger.error(f"{error_msg} for DRPID: {drpid}")
            return self._result
        self._result["folder_path"] = str(folder_path)
        
        try:
            # Initialize browser and load page
            if not self._init_browser_and_load_page(url):
                return self._result
            
            # Process page and generate PDF
            self._process_and_generate_pdf(folder_path)
            
            # Download dataset and extract metadata
            self._download_dataset_and_extract_metadata(folder_path)
            
        except Exception as e:
            error_msg = f"Collection error: {str(e)}"
            Logger.exception(error_msg)
            self._append_result_note(error_msg)
        finally:
            self._cleanup_browser()
        
        return self._result
    
    def _validate_and_access_url(self, url: str) -> bool:
        """
        Validate URL and check accessibility.
        
        Updates result status on failure.
        
        Args:
            url: URL to validate and access
            
        Returns:
            True if URL is valid and accessible, False otherwise
        """
        if not is_valid_url(url):
            self._result["collection_notes"] = "Invalid URL"
            Logger.warning(f"Invalid URL: {url}")
            return False

        access_success, status_msg = access_url(url)
        if not access_success:
            self._result["collection_notes"] = status_msg
            Logger.warning(f"URL access failed: {url} - {status_msg}")
            return False

        self._result["collection_notes"] = status_msg
        Logger.info(f"Successfully accessed URL: {url}")
        return True
    
    def _init_browser_and_load_page(self, url: str) -> bool:
        """
        Initialize browser and load the page.
        
        Updates result status on failure.
        
        Args:
            url: URL to load
            
        Returns:
            True if successful, False otherwise
        """
        if not self._init_browser():
            error_msg = "Failed to initialize browser"
            self._append_result_note(error_msg)
            return False

        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=120000)
            self._page.wait_for_timeout(500)
            return True
        except Exception as e:
            error_msg = f"Failed to load page: {str(e)}"
            self._append_result_note(error_msg)
            Logger.error(error_msg)
            return False
    
    def _process_and_generate_pdf(self, folder_path: Path) -> None:
        """
        Process page and generate PDF.
        
        PDF filename uses the original page title (sanitized).
        
        Args:
            folder_path: Folder where PDF should be saved
        """
        page_processor = SocrataPageProcessor(self)
        
        # Get page title for PDF filename
        try:
            page_title = self._page.title()
            if page_title:
                pdf_filename = sanitize_filename(page_title, max_length=100) + ".pdf"
            else:
                # Fallback if no title
                pdf_filename = "page.pdf"
        except Exception:
            pdf_filename = "page.pdf"
        
        pdf_path = folder_path / pdf_filename
        page_processor.generate_pdf(pdf_path)
    
    def _download_dataset_and_extract_metadata(self, folder_path: Path) -> None:
        """
        Download dataset and extract metadata.
        
        Dataset filename uses the original filename from the download (sanitized).
        
        Args:
            folder_path: Folder where dataset should be saved
        """
        dataset_downloader = SocrataDatasetDownloader(self)
        dataset_downloader.download(folder_path)
        
        # Extract metadata
        metadata_extractor = SocrataMetadataExtractor(self)
        metadata_extractor.extract_all_metadata()
    
    def _append_result_note(self, note: str) -> None:
        """
        Append a note to the ``collection_notes`` field in the result dict.
        
        Args:
            note: Note to append (e.g. status message, error, warning).
        """
        existing = self._result.get("collection_notes")
        if existing:
            self._result["collection_notes"] = f"{existing}; {note}"
        else:
            self._result["collection_notes"] = note
    
    def _init_browser(self) -> bool:
        """
        Initialize Playwright browser and page.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self._headless,
                slow_mo=500 if not self._headless else 0
            )
            self._page = self._browser.new_page()
            return True
        except Exception as e:
            Logger.error(f"Failed to initialize browser: {e}")
            self._cleanup_browser()
            return False
    
    def _cleanup_browser(self) -> None:
        """Clean up browser resources."""
        if self._browser:
            with suppress(Exception):
                self._browser.close()
            self._browser = None
        
        if self._playwright:
            with suppress(Exception):
                self._playwright.stop()
            self._playwright = None
        
        self._page = None
    
    def _update_storage_from_result(self, drpid: int, result: Dict[str, Any]) -> None:
        """
        Transfer result dict to Storage.
        
        Only keys that are Storage column names and have non-None values are
        written. Sets status to "collectors" on success or "Error" on failure,
        and appends collection_notes to errors/warnings as appropriate.
        
        Args:
            drpid: The DRPID of the project.
            result: Flat result dict from collect() (Storage field names).
        """
        collection_notes = result.get("collection_notes") or ""
        has_folder = bool(result.get("folder_path"))
        has_success_note = (
            "PDF generated" in collection_notes or "Dataset downloaded" in collection_notes
        )
        notes_lower = collection_notes.lower()
        has_error_note = (
            "invalid url" in notes_lower
            or "connection error" in notes_lower
            or "failed to" in notes_lower
            or notes_lower.startswith("error")
            or " collection error:" in notes_lower
        )

        # Set status: success if we have folder and some success note and no error
        if has_error_note:
            result = {**result, "status": "Error"}
            Storage.append_to_field(drpid, "errors", collection_notes)
        elif has_folder and has_success_note:
            result = {**result, "status": "collectors"}

        # Append to warnings when notes contain warning/skipped (even on success)
        if "warning" in notes_lower or "skipped" in notes_lower:
            Storage.append_to_field(drpid, "warnings", collection_notes)

        # Transfer only Storage columns with non-None values
        update_fields = {
            k: v for k, v in result.items()
            if k in _STORAGE_FIELDS and v is not None
        }
        if update_fields:
            Storage.update_record(drpid, update_fields)
