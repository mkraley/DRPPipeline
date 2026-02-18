"""
DataLumos file upload handler.

Handles uploading files to a DataLumos project using Playwright.
Uses a drop-zone compatible approach: injects a file input and dispatches
drag/drop events to the modal drop target so the UI receives files.
"""

from pathlib import Path
from typing import List

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from utils.Logger import Logger


# Selectors from DataLumos import file modal (aligned with chiara_upload.py)
UPLOAD_BTN_SELECTOR = "a.btn-primary:nth-child(3) > span:nth-child(4)"
DROP_ZONE_SELECTOR = ".importFileModal .col-md-offset-2 > span:nth-child(1)"
FILE_QUEUED_TEXT = "File added to queue for upload."
CLOSE_MODAL_SELECTOR = ".importFileModal > div:nth-child(3) > button:nth-child(1)"
INJECTED_INPUT_ID = "pw-datalumos-file-input"

# JS to create file input and dispatch drop events to target (adapted from chiara/Selenium approach)
JS_INJECT_FILE_INPUT = """
(selector) => {
  const target = document.querySelector(selector);
  if (!target) return null;
  const input = document.createElement('input');
  input.type = 'file';
  input.id = '""" + INJECTED_INPUT_ID + """';
  input.style.display = 'none';
  input.onchange = function () {
    const rect = target.getBoundingClientRect();
    const x = rect.left + (rect.width >> 1);
    const y = rect.top + (rect.height >> 1);
    const dataTransfer = { files: this.files };
    ['dragenter', 'dragover', 'drop'].forEach(function (name) {
      const evt = document.createEvent('MouseEvent');
      evt.initMouseEvent(name, true, true, window, 0, 0, 0, x, y, false, false, false, false, 0, null);
      Object.defineProperty(evt, 'dataTransfer', { value: dataTransfer });
      target.dispatchEvent(evt);
    });
    this.value = '';
  };
  document.body.appendChild(input);
  return input.id;
}
"""


class DataLumosFileUploader:
    """
    Handles file uploads to DataLumos.
    
    Uses Playwright's set_input_files on an injected file input whose onchange
    dispatches drag/drop events to the modal drop zone.
    """

    def __init__(self, page: Page, timeout: int = 120000, upload_wait_timeout: int = 600000) -> None:
        """
        Initialize the file uploader.

        Args:
            page: Playwright Page object
            timeout: Default timeout in milliseconds for UI actions
            upload_wait_timeout: Timeout in ms to wait for all files to be queued (default 10 min)
        """
        self._page = page
        self._timeout = timeout
        self._upload_wait_timeout = upload_wait_timeout

    def upload_files(self, folder_path: str) -> None:
        """
        Upload all files from a folder to the current DataLumos project.

        Opens the Upload Files modal, injects a file input that feeds the drop zone,
        sets files one-by-one, waits for all to be queued, then closes the modal.

        Args:
            folder_path: Path to folder containing files to upload

        Raises:
            FileNotFoundError: If folder doesn't exist
            RuntimeError: If upload flow fails
        """
        files = self.get_file_paths(folder_path)
        if not files:
            Logger.info(f"No files to upload in {folder_path}")
            return

        Logger.info(f"Uploading {len(files)} file(s) from {folder_path}")
        self._wait_for_obscuring_elements()

        upload_btn = self._page.locator(UPLOAD_BTN_SELECTOR)
        upload_btn.click()
        self._page.wait_for_timeout(1000)
        self._wait_for_obscuring_elements()

        drop_zone = self._page.locator(DROP_ZONE_SELECTOR)
        drop_zone.wait_for(state="visible", timeout=self._timeout)

        input_id = self._page.evaluate(JS_INJECT_FILE_INPUT, DROP_ZONE_SELECTOR)
        if not input_id:
            raise RuntimeError("Could not find drop zone for file upload")

        file_input = self._page.locator(f"#{input_id}")
        for path in files:
            try:
                file_input.set_input_files(str(path))
                self._page.wait_for_timeout(500)
            except Exception as e:
                self._remove_injected_input()
                raise RuntimeError(f"Error uploading file '{path.name}': {e}") from e

        self.wait_for_upload_completion(len(files))
        self._remove_injected_input()

        close_btn = self._page.locator(CLOSE_MODAL_SELECTOR)
        close_btn.click()
        self._wait_for_obscuring_elements()
        Logger.info("File upload completed and modal closed")

    def _remove_injected_input(self) -> None:
        """Remove the injected file input from the DOM."""
        try:
            self._page.evaluate(
                f"() => {{ const el = document.getElementById('{INJECTED_INPUT_ID}'); if (el) el.remove(); }}"
            )
        except Exception:
            pass

    def _wait_for_obscuring_elements(self) -> None:
        """Wait for busy overlay to disappear."""
        busy = self._page.locator("#busy")
        try:
            if busy.count() > 0:
                busy.first.wait_for(state="hidden", timeout=360000)
                self._page.wait_for_timeout(500)
        except PlaywrightTimeoutError:
            Logger.warning("Timeout waiting for busy overlay to disappear")

    def get_file_paths(self, folder_path: str) -> List[Path]:
        """
        Get list of file paths to upload from a folder.

        Args:
            folder_path: Path to folder containing files

        Returns:
            List of Path objects for files (not subdirectories)

        Raises:
            FileNotFoundError: If folder doesn't exist
            NotADirectoryError: If path is not a directory
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {folder_path}")
        files = [f for f in folder.iterdir() if f.is_file()]
        Logger.debug(f"Found {len(files)} files in {folder_path}")
        return files

    def wait_for_upload_completion(self, file_count: int) -> None:
        """
        Wait for all file uploads to be queued.

        Waits until the text "File added to queue for upload." appears
        at least file_count times (or timeout).

        Args:
            file_count: Number of files being uploaded

        Raises:
            TimeoutError: If uploads don't complete within upload_wait_timeout
        """
        if file_count <= 0:
            return
        queued = self._page.locator(f"span:has-text('{FILE_QUEUED_TEXT}')")
        try:
            queued.nth(file_count - 1).wait_for(state="visible", timeout=self._upload_wait_timeout)
        except PlaywrightTimeoutError as e:
            raise TimeoutError(
                f"File upload did not complete within {self._upload_wait_timeout} ms "
                f"(expected {file_count} 'File added to queue for upload.' messages)"
            ) from e
        Logger.debug(f"All {file_count} file(s) added to queue")
