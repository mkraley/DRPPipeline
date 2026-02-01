"""
Socrata Dataset Downloader for DRP Pipeline.

Handles downloading datasets from Socrata pages via Export/Download buttons.
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from utils.Args import Args
from utils.Errors import record_error
from utils.file_utils import format_file_size, sanitize_filename
from utils.Logger import Logger
from utils.download_with_progress import download_via_url

if TYPE_CHECKING:
    from collectors.SocrataCollector import SocrataCollector


def _get_socrata_view_id_from_url(url: str) -> Optional[str]:
    """
    Extract Socrata view_id from a dataset page URL.
    e.g. .../yctb-fv7w/about_data -> yctb-fv7w (segment before about_data).
    """
    parsed = urlparse(url)
    segments = [s for s in (parsed.path or "").split("/") if s]
    if not segments:
        return None
    if "about_data" in segments:
        i = segments.index("about_data")
        return segments[i - 1] if i > 0 else None
    return segments[-1]


def _build_socrata_export_url(page_url: str, view_id: str) -> str:
    """
    Build Socrata export URL from page origin and view_id.
    e.g. https://data.cdc.gov/api/v3/views/yctb-fv7w/export.csv?accessType=DOWNLOAD
    """
    parsed = urlparse(page_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return f"{origin}/api/v3/views/{view_id}/export.csv?accessType=DOWNLOAD"


def _is_socrata_export_url(url: str) -> bool:
    """
    True if URL looks like a Socrata dataset export (e.g. data.cdc.gov API).
    Pattern: .../api/.../views/{view_id}/export.csv?... or .../export...
    """
    return "/views/" in url and "export" in url.lower()


def _extension_from_export_url(url: str) -> str:
    """Get file extension from Socrata export URL (e.g. export.csv -> csv)."""
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    if path:
        name = path.rsplit("/", 1)[-1]
        if "." in name:
            return name.rsplit(".", 1)[-1].lower()
    qs = parse_qs(parsed.query)
    fmt = (qs.get("format") or [None])[0]
    if fmt:
        return "csv" if fmt.lower() == "csv" else "json" if fmt.lower() == "json" else fmt.lower()
    return "csv"


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
        Download dataset. When use_url_download and the page URL has a Socrata view_id,
        construct the export URL directly and download (no Export dialog). Otherwise
        open the Export dialog and use the dialog path (interception or save_as).
        Updates result with download status, path, extension, and size.
        """
        if timeout is None:
            timeout = getattr(Args, "download_timeout_ms", 30 * 60 * 1000) or 30 * 60 * 1000
        use_url_download = getattr(Args, "use_url_download", True)
        page = self._collector._page

        try:
            # When use_url_download, try to construct Socrata export URL from page URL
            # (e.g. .../yctb-fv7w/about_data -> .../api/v3/views/yctb-fv7w/export.csv?...)
            if use_url_download:
                view_id = _get_socrata_view_id_from_url(page.url)
                if view_id:
                    try:
                        return self._download_via_constructed_url(
                            folder_path, timeout, view_id
                        )
                    except requests.HTTPError as e:
                        if e.response is not None and e.response.status_code in (401, 403):
                            Logger.warning(
                                "Direct download returned %s (auth required), falling back to Export dialog",
                                e.response.status_code,
                            )
                        else:
                            raise

            # Open Export dialog, then _download_file (browser session; or save_as)
            if not self._click_export_button():
                record_error(self._collector._drpid, "Export button not found")
                return False
            page.wait_for_timeout(1000)
            return self._download_file(folder_path, timeout)

        except PlaywrightTimeoutError:
            record_error(self._collector._drpid, "Timeout waiting for download")
            return False
        except Exception as e:
            Logger.exception("Error downloading dataset: %s", e)
            error_msg = f"Error downloading dataset: {str(e)[:100]}"
            record_error(self._collector._drpid, error_msg)
            return False
    
    def _download_via_constructed_url(
        self, folder_path: Path, timeout: int, view_id: str
    ) -> bool:
        """
        Build Socrata export URL from view_id and download via requests (no dialog).
        Filename from page title (sanitized), extension .csv.
        """
        page = self._collector._page
        export_url = _build_socrata_export_url(page.url, view_id)
        cookies = page.context.cookies()
        try:
            stem = sanitize_filename(page.title(), max_length=100) if page.title() else "dataset"
        except Exception:
            stem = "dataset"
        dataset_filename = f"{stem}.csv"
        dataset_path = folder_path / dataset_filename
        timeout_sec = (timeout // 1000) if timeout else 3600
        app_token = getattr(Args, "socrata_app_token", None)
        extra_headers = {"X-App-Token": app_token} if app_token else None
        bytes_written, ok = download_via_url(
            export_url,
            dataset_path,
            cookies=cookies,
            headers=extra_headers,
            progress_interval_mb=50.0,
            resume=True,
            timeout_sec=timeout_sec,
        )
        if not ok:
            record_error(self._collector._drpid, "URL download failed")
            return False
        file_extension = self._get_file_extension(dataset_path)
        pdf_size = sum(f.stat().st_size for f in folder_path.glob("*.pdf") if f.exists())
        total_size = bytes_written + pdf_size
        self._collector._result["file_size"] = str(total_size)
        self._collector._result["extensions"] = f"pdf, {file_extension}" if file_extension else "pdf"
        self._collector._result["download_date"] = datetime.now().strftime("%Y-%m-%d")
        return True

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
        
        If use_url_download: register for the download-start event, click, capture
        the Download as soon as the event fires, cancel the browser download, then
        download via requests with progress/resume.
        Otherwise: use expect_download + save_as (with 30s "still in progress" warning).
        Updates result with dataset path, extension, and size.
        
        Args:
            folder_path: Folder where file should be saved
            timeout: Timeout in milliseconds
            
        Returns:
            True if successful, False otherwise
        """
        use_url_download = getattr(Args, "use_url_download", True)
        page = self._collector._page
        download_button = self._find_download_button()
        if download_button is None:
            record_error(self._collector._drpid, "Download button not found in dialog")
            return False

        if use_url_download:
            # Capture the export URL via request interception (download event often
            # doesn't fire for Socrata). Intercept the request, abort it, then
            # download ourselves with progress/resume.
            url_holder: List[str] = []
            url_received = threading.Event()

            def handle_route(route) -> None:
                req = route.request
                url = req.url
                # Socrata export: .../api/.../views/{view_id}/export.csv?... (e.g. data.cdc.gov)
                if not url_holder and _is_socrata_export_url(url):
                    url_holder.append(url)
                    url_received.set()
                    try:
                        route.abort()
                    except Exception:
                        pass
                    return
                try:
                    route.continue_()
                except Exception:
                    pass

            page.route("**/*", handle_route)
            try:
                try:
                    download_button.scroll_into_view_if_needed()
                    download_button.click()
                except Exception as e:
                    record_error(self._collector._drpid, f"Could not click Download button: {str(e)}")
                    return False
                wait_sec = min(300, max(30, timeout // 1000))
                Logger.info("Waiting for export request (up to %ds)...", wait_sec)
                if not url_received.wait(timeout=wait_sec):
                    record_error(
                        self._collector._drpid,
                        "Export request not captured within timeout (%ds)" % wait_sec,
                    )
                    return False
                captured_url = url_holder[0]
            finally:
                try:
                    page.unroute("**/*")
                except Exception:
                    pass

            # Filename from page title (sanitized), extension from URL (e.g. export.csv -> .csv)
            try:
                page_title = page.title()
                stem = sanitize_filename(page_title, max_length=100) if page_title else "dataset"
            except Exception:
                stem = "dataset"
            ext = _extension_from_export_url(captured_url)
            dataset_filename = f"{stem}.{ext}"
            dataset_path = folder_path / dataset_filename
            cookies = page.context.cookies()
            timeout_sec = (timeout // 1000) if timeout else 3600
            bytes_written, ok = download_via_url(
                captured_url,
                dataset_path,
                cookies=cookies,
                progress_interval_mb=50.0,
                resume=True,
                timeout_sec=timeout_sec,
            )
            if not ok:
                record_error(self._collector._drpid, "URL download failed")
                return False
            dataset_size = bytes_written
            # Skip the "suggested_filename" / download block below; we already set result
            file_extension = self._get_file_extension(dataset_path)
            pdf_size = sum(f.stat().st_size for f in folder_path.glob("*.pdf") if f.exists())
            total_size = dataset_size + pdf_size
            self._collector._result["file_size"] = str(total_size)
            self._collector._result["extensions"] = f"pdf, {file_extension}" if file_extension else "pdf"
            self._collector._result["download_date"] = datetime.now().strftime("%Y-%m-%d")
            return True
        else:
            with page.expect_download(timeout=timeout) as download_info:
                try:
                    download_button.scroll_into_view_if_needed()
                    download_button.click()
                except Exception as e:
                    record_error(self._collector._drpid, f"Could not click Download button: {str(e)}")
                    return False
            download = download_info.value
            suggested_filename = download.suggested_filename
            if suggested_filename:
                original_name = Path(suggested_filename).stem
                file_extension = Path(suggested_filename).suffix[1:] if Path(suggested_filename).suffix else None
                sanitized_name = sanitize_filename(original_name, max_length=100)
                dataset_filename = f"{sanitized_name}.{file_extension}" if file_extension else sanitized_name
            else:
                dataset_filename = "dataset.csv"
            dataset_path = folder_path / dataset_filename
            download_done: threading.Event = threading.Event()
            download_thread_id = Logger.get_thread_id()
            drpid = self._collector._drpid

            def _warn_if_still_downloading() -> None:
                time.sleep(30)
                if not download_done.is_set():
                    Logger.warning(
                        "Thread T%s DRPID %s: Download still in progress (running > 30 s) - may be a large file",
                        download_thread_id,
                        drpid,
                    )

            timer = threading.Thread(target=_warn_if_still_downloading, daemon=True)
            timer.start()
            try:
                start_time = time.perf_counter()
                download.save_as(dataset_path)
                elapsed_sec = time.perf_counter() - start_time
                dataset_size = dataset_path.stat().st_size if dataset_path.exists() else 0
                size_mb = dataset_size / (1024 * 1024)
                rate_mb_per_sec = size_mb / elapsed_sec if elapsed_sec > 0 else 0.0
                Logger.info(
                    f"Dataset downloaded in {elapsed_sec:.1f}s: {dataset_path.name} "
                    f"({format_file_size(dataset_size)}, {rate_mb_per_sec:.2f} MB/s)"
                )
            finally:
                download_done.set()

        file_extension = self._get_file_extension(dataset_path)
        pdf_size = sum(f.stat().st_size for f in folder_path.glob("*.pdf") if f.exists())
        total_size = dataset_size + pdf_size

        self._collector._result["file_size"] = str(total_size)
        self._collector._result["extensions"] = f"pdf, {file_extension}" if file_extension else "pdf"
        self._collector._result["download_date"] = datetime.now().strftime("%Y-%m-%d")
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
