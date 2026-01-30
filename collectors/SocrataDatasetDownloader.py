"""
Socrata Dataset Downloader for DRP Pipeline.

Handles downloading datasets from Socrata pages via Export/Download buttons.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.Errors import record_error, record_warning
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
    
    def download(self, folder_path: Path, timeout: int = 60000) -> bool:
        """
        Download dataset by clicking Export button and then Download button.
        
        Updates result directly with download status, path, extension, and size.
        Uses the original filename from the download with sanitization.
        
        Args:
            folder_path: Folder where the downloaded file should be saved
            timeout: Timeout in milliseconds
            
        Returns:
            True if download was successful, False otherwise
        """
        try:
            # Click Export button
            if not self._click_export_button():
                record_error(self._collector._drpid, "Export button not found")
                return False
            
            # Wait for dialog
            self._collector._page.wait_for_timeout(1000)
            
            # Check for large dataset warning
            if self._has_large_dataset_warning():
                record_warning(self._collector._drpid, "Large dataset warning - download skipped")
                return False
            
            # Download the file
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
    
    def _has_large_dataset_warning(self) -> bool:
        """
        Check if there's a large dataset warning dialog.
        
        Returns:
            True if warning is present, False otherwise
        """
        try:
            warning_element = self._collector._page.locator('div.message-title[slot="title"]')
            warning_count = warning_element.count()
            if warning_count > 0:
                warning_text = warning_element.first.inner_text().strip()
                return 'Large dataset warning' in warning_text
        except Exception:
            pass
        return False
    
    def _download_file(self, folder_path: Path, timeout: int) -> bool:
        """
        Find Download button, click it, and save the file.
        
        Updates result with dataset path, extension, and size.
        Uses the original filename from the download with sanitization.
        
        Args:
            folder_path: Folder where file should be saved
            timeout: Timeout in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        with self._collector._page.expect_download(timeout=timeout) as download_info:
            download_button = self._find_download_button()
            if download_button is None:
                record_error(self._collector._drpid, "Download button not found in dialog")
                return False
            
            try:
                download_button.scroll_into_view_if_needed()
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
            # Fallback if no suggested filename
            dataset_filename = "dataset.csv"
        
        dataset_path = folder_path / dataset_filename
        download.save_as(dataset_path)
        
        # Get file size after saving
        file_size = None
        if dataset_path.exists():
            file_size = dataset_path.stat().st_size
        
        # Get file extension
        file_extension = self._get_file_extension(dataset_path)
        
        # Update result (Storage field names)
        if file_size is not None:
            self._collector._result["file_size"] = str(file_size)
        self._collector._result["download_date"] = datetime.now().strftime("%Y-%m-%d")
        record_warning(self._collector._drpid, f"Dataset downloaded: {dataset_path.name}")
        Logger.info(f"Dataset downloaded: {dataset_path} (size: {file_size} bytes)")
        return True
    
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
