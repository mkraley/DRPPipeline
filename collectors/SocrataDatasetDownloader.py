"""
Socrata Dataset Downloader for DRP Pipeline.

Handles downloading datasets from Socrata pages via Export/Download buttons.
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Errors import record_error
from utils.file_utils import format_file_size
from utils.Logger import Logger

if TYPE_CHECKING:
    from collectors.SocrataCollector import SocrataCollector


class SocrataDatasetDownloader:
    """
    Downloads datasets from Socrata pages.
    
    Handles the download workflow:
    - Finding and clicking Export button
    - Checking for warnings
    - Finding and clicking Download button
    - Saving the downloaded file
    """
    
    def __init__(self, collector: "SocrataCollector") -> None:
        """
        Initialize SocrataDatasetDownloader with a SocrataCollector instance.
        
        Args:
            collector: SocrataCollector instance to access page and result
        """
        self._collector = collector
    
    def download(self, folder_path: Path, timeout: Optional[int] = None) -> bool:
        """
        Download dataset by clicking Export button and then Download button.
        
        Updates result directly with download status, path, extension, and size.
        Uses the original filename from the download with sanitization.
        Timeout defaults to Args.download_timeout_ms (e.g. 30 min for large datasets).
        
        Args:
            folder_path: Folder where the downloaded file should be saved
            timeout: Timeout in milliseconds; None = use Args.download_timeout_ms
            
        Returns:
            True if download was successful, False otherwise
        """
        if timeout is None:
            timeout = getattr(Args, "download_timeout_ms", 30 * 60 * 1000) or 30 * 60 * 1000
        try:
            # Click Export button
            if not self._click_export_button():
                record_error(self._collector._drpid, "Export button not found")
                return False
            
            # Wait for dialog
            self._collector._page.wait_for_timeout(1000)
            
            # Download the file (no longer skip based on Socrata large-dataset warning)
            return self._download_file(folder_path, timeout)
        
        except PlaywrightTimeoutError:
            record_error(self._collector._drpid, "Timeout waiting for download")
            return False
        except Exception as e:
            error_msg = f"Error downloading dataset: {str(e)[:100]}"
            record_error(self._collector._drpid, error_msg)
            return False
    
    def _click_export_button(self) -> bool:
        """
        Find and click the Export button using precise locator.
        
        Uses forge-button with data-testid="export-data-button".
        
        Returns:
            True if button was found and clicked, False otherwise
        """
        try:
            export_button = self._collector._page.locator('forge-button[data-testid="export-data-button"]')
            if export_button.count() > 0:
                export_button.first.scroll_into_view_if_needed()
                export_button.first.click()
                return True
        except Exception:
            pass
        return False
    
    def _download_file(self, folder_path: Path, timeout: int) -> bool:
        """
        Find Download button, click it, and save the file.
        
        If the download is still in progress after 30 seconds, logs a WARNING
        that it may be a large file. Updates result with dataset path, extension, and size.
        Uses the original filename from the download with sanitization.
        
        Args:
            folder_path: Folder where file should be saved
            timeout: Timeout in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        download_done: threading.Event = threading.Event()

        def _warn_if_still_downloading() -> None:
            time.sleep(30)
            if not download_done.is_set():
                Logger.warning(
                    "Download still in progress (running > 30 s) - may be a large file"
                )

        timer = threading.Thread(target=_warn_if_still_downloading, daemon=True)
        timer.start()
        try:
            with self._collector._page.expect_download(timeout=timeout) as download_info:
                download_button = self._find_download_button()
                if download_button is None:
                    record_error(self._collector._drpid, "Download button not found in dialog")
                    return False

                try:
                    download_button.scroll_into_view_if_needed()
                    start_time = time.perf_counter()
                    download_button.click()
                except Exception as e:
                    record_error(self._collector._drpid, f"Could not click Download button: {str(e)}")
                    return False

            # Save the downloaded file
            download = download_info.value
            suggested_filename = download.suggested_filename

            # Use original filename with sanitization, or fallback to generic name
            if suggested_filename:
                from utils.file_utils import sanitize_filename
                original_name = Path(suggested_filename).stem
                file_extension = Path(suggested_filename).suffix[1:] if Path(suggested_filename).suffix else None
                sanitized_name = sanitize_filename(original_name, max_length=100)
                if file_extension:
                    dataset_filename = f"{sanitized_name}.{file_extension}"
                else:
                    dataset_filename = sanitized_name
            else:
                dataset_filename = "dataset.csv"

            dataset_path = folder_path / dataset_filename
            download.save_as(dataset_path)
            elapsed_sec = time.perf_counter() - start_time

            # Get file size after saving
            dataset_size = dataset_path.stat().st_size if dataset_path.exists() else 0

            # Get file extension
            file_extension = self._get_file_extension(dataset_path)

            # Sum downloaded file size plus PDF(s) created earlier in this folder
            pdf_size = sum(f.stat().st_size for f in folder_path.glob("*.pdf") if f.exists())
            total_size = dataset_size + pdf_size

            # Log download time, size, and rate (MB/sec)
            size_mb = dataset_size / (1024 * 1024)
            rate_mb_per_sec = size_mb / elapsed_sec if elapsed_sec > 0 else 0.0
            Logger.info(
                f"Dataset downloaded in {elapsed_sec:.1f}s: {dataset_path.name} "
                f"({format_file_size(dataset_size)}, {rate_mb_per_sec:.2f} MB/s)"
            )

            # Update result (Storage field names)
            self._collector._result["file_size"] = str(total_size)
            self._collector._result["data_types"] = f"pdf, {file_extension}" if file_extension else "pdf"
            self._collector._result["download_date"] = datetime.now().strftime("%Y-%m-%d")
            return True
        finally:
            download_done.set()

    def _find_download_button(self):
        """
        Find the Download button in the dialog using precise locator.
        
        Uses forge-button with data-testid="export-download-button".
        
        Returns:
            Button locator if found, None otherwise
        """
        try:
            download_button = self._collector._page.locator('forge-button[data-testid="export-download-button"]')
            if download_button.count() > 0:
                return download_button.first
        except Exception:
            pass
        return None
    
    def _get_file_extension(self, dataset_path: Path) -> Optional[str]:
        """
        Get file extension from saved file.
        
        Args:
            dataset_path: Path where file was saved
            
        Returns:
            File extension (without dot) or None
        """
        if dataset_path.exists():
            ext_with_dot = dataset_path.suffix
            if ext_with_dot:
                return ext_with_dot[1:].lower()
        return None
