"""
Socrata Dataset Downloader for DRP Pipeline.

Handles downloading datasets from Socrata pages via Export/Download buttons.
"""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

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
    
    def download(self, dataset_path: Path, timeout: int = 60000) -> bool:
        """
        Download dataset by clicking Export button and then Download button.
        
        Updates result directly with download status, path, extension, and size.
        
        Args:
            dataset_path: Path where the downloaded file should be saved
            timeout: Timeout in milliseconds
            
        Returns:
            True if download was successful, False otherwise
        """
        try:
            # Click Export button
            if not self._click_export_button():
                self._collector._update_status('Export button not found')
                return False
            
            # Wait for dialog
            self._collector._page.wait_for_timeout(1000)
            
            # Check for large dataset warning
            if self._has_large_dataset_warning():
                self._collector._update_status('Large dataset warning - download skipped')
                return False
            
            # Download the file
            return self._download_file(dataset_path, timeout)
        
        except PlaywrightTimeoutError:
            self._collector._update_status("Timeout waiting for download")
            return False
        except Exception as e:
            error_msg = f"Error downloading dataset: {str(e)[:100]}"
            self._collector._update_status(error_msg)
            return False
    
    def _click_export_button(self) -> bool:
        """
        Find and click the Export button.
        
        Returns:
            True if button was found and clicked, False otherwise
        """
        all_buttons = self._collector._page.locator('button, a, [role="button"]')
        button_count = all_buttons.count()
        
        for i in range(button_count):
            try:
                button = all_buttons.nth(i)
                text = button.inner_text().strip().lower()
                if 'export' in text and len(text) < 50:
                    button.scroll_into_view_if_needed()
                    button.click()
                    return True
            except Exception:
                continue
        
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
    
    def _download_file(self, dataset_path: Path, timeout: int) -> bool:
        """
        Find Download button, click it, and save the file.
        
        Updates result with dataset path, extension, and size.
        
        Args:
            dataset_path: Path where file should be saved
            timeout: Timeout in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        with self._collector._page.expect_download(timeout=timeout) as download_info:
            download_button = self._find_download_button()
            if download_button is None:
                self._collector._update_status('Download button not found in dialog')
                return False
            
            try:
                download_button.scroll_into_view_if_needed()
                download_button.click()
            except Exception as e:
                self._collector._update_status(f'Could not click Download button: {str(e)}')
                return False
        
        # Save the downloaded file
        download = download_info.value
        file_extension = self._get_file_extension(download, dataset_path)
        download.save_as(dataset_path)
        
        # Get file size after saving
        file_size = None
        if dataset_path.exists():
            file_size = dataset_path.stat().st_size
        
        # Update result
        self._collector._result['dataset_path'] = str(dataset_path)
        if file_extension:
            self._collector._result['file_extensions'].append(file_extension)
        if file_size is not None:
            self._collector._result['dataset_size'] = file_size
        
        self._collector._update_status(f"Dataset downloaded: {dataset_path.name}")
        Logger.info(f"Dataset downloaded: {dataset_path} (size: {file_size} bytes)")
        return True
    
    def _find_download_button(self):
        """
        Find the Download button in the dialog.
        
        Returns:
            Button locator if found, None otherwise
        """
        # First try all buttons
        all_buttons = self._collector._page.locator('button, a, [role="button"]')
        button_count = all_buttons.count()
        
        for i in range(button_count):
            try:
                button = all_buttons.nth(i)
                if button.inner_text().strip() == 'Download':
                    return button
            except Exception:
                continue
        
        # Try looking in dialogs if not found
        dialogs = self._collector._page.locator('dialog, [role="dialog"], .modal, [class*="dialog"]')
        dialog_count = dialogs.count()
        for i in range(dialog_count):
            dialog = dialogs.nth(i)
            dialog_buttons = dialog.locator('button, a, [role="button"]')
            dialog_button_count = dialog_buttons.count()
            for j in range(dialog_button_count):
                try:
                    button = dialog_buttons.nth(j)
                    if button.inner_text().strip() == 'Download':
                        return button
                except Exception:
                    continue
        
        return None
    
    def _get_file_extension(self, download, dataset_path: Path) -> Optional[str]:
        """
        Get file extension from download or saved file.
        
        Args:
            download: Playwright download object
            dataset_path: Path where file was saved
            
        Returns:
            File extension (without dot) or None
        """
        # Try from suggested filename
        suggested_filename = download.suggested_filename
        if suggested_filename:
            ext_with_dot = Path(suggested_filename).suffix
            if ext_with_dot:
                return ext_with_dot[1:].lower()
        
        # Try from saved file
        if dataset_path.exists():
            ext_with_dot = dataset_path.suffix
            if ext_with_dot:
                return ext_with_dot[1:].lower()
        
        return None
