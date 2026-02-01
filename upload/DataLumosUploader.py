"""
DataLumos uploader module.

Implements ModuleProtocol to upload collected data to DataLumos.
Coordinates browser lifecycle, authentication, form filling, and file uploads.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from storage import Storage
from utils.Args import Args
from utils.Errors import record_error
from utils.Logger import Logger


class DataLumosUploader:
    """
    Upload module that uploads collected project data to DataLumos.
    
    Implements ModuleProtocol. For each eligible project (status="collector"),
    this module: authenticates, creates project, fills form fields,
    and updates Storage with datalumos_id.
    
    Prerequisites: status="collector" and no errors
    Success status: status="upload"
    """
    
    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
    
    def __init__(self) -> None:
        """Initialize the DataLumos uploader. Config from Args."""
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._authenticated = False
    
    def run(self, drpid: int) -> None:
        """
        Run the upload process for a single project.
        
        Implements ModuleProtocol. Gets project from Storage, validates,
        uploads to DataLumos, and updates Storage on success.
        
        Args:
            drpid: The DRPID of the project to upload.
        """
        Logger.info(f"Starting upload for DRPID={drpid}")
        
        project = Storage.get(drpid)
        if project is None:
            record_error(drpid, f"Project with DRPID={drpid} not found in Storage")
            return
        
        errors = self._validate_project(project)
        if errors:
            for error in errors:
                record_error(drpid, error)
            return

        source_url = self._get_field(project, "source_url")
        if source_url:
            page = self._ensure_browser()
            from upload.GWDANominator import GWDANominator
            nominator = GWDANominator(page, timeout=Args.upload_timeout)
            success, error = nominator.nominate(source_url)
            if not success:
                record_error(drpid, error or "GWDA nomination failed")
                return

        try:
            datalumos_id = self._upload_project(project, drpid)
            Storage.update_record(drpid, {
                "datalumos_id": datalumos_id,
                "status": "upload",
            })
            Logger.info(f"Upload completed for DRPID={drpid}, datalumos_id={datalumos_id}")
        except Exception as e:
            record_error(drpid, f"Upload failed: {e}")
            raise
        finally:
            self.close()
    
    def _validate_project(self, project: Dict[str, Any]) -> list[str]:
        """Validate required fields. Returns list of error messages."""
        errors: list[str] = []
        if not self._get_field(project, "title"):
            errors.append("Missing required field: title")
        if not self._get_field(project, "summary"):
            errors.append("Missing required field: summary")
        
        folder = self._get_field(project, "folder_path")
        if folder:
            path = Path(folder)
            if not path.exists():
                errors.append(f"Folder path does not exist: {folder}")
            elif not path.is_dir():
                errors.append(f"Folder path is not a directory: {folder}")
        
        return errors
    
    def _get_field(self, project: Dict[str, Any], key: str) -> str:
        """Get and trim a project field. Returns empty string if missing."""
        return (project.get(key) or "").strip()
    
    def _project_url(self, workspace_id: str) -> str:
        """Build URL for a DataLumos project page."""
        return f"{self.WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"

    def _upload_project(self, project: Dict[str, Any], drpid: int) -> str:
        """
        Upload a project to DataLumos.
        
        If project already has datalumos_id, navigates directly to that project
        and continues with form filling. Otherwise creates a new project, saves
        datalumos_id to Storage immediately, then fills the form.
        
        Returns:
            The DataLumos workspace ID.
        """
        page = self._ensure_browser()
        self._ensure_authenticated()
        
        from upload.DataLumosFormFiller import DataLumosFormFiller
        
        form_filler = DataLumosFormFiller(page, timeout=Args.upload_timeout)
        
        existing_id = self._get_field(project, "datalumos_id")
        
        if existing_id:
            Logger.info(f"Resuming upload for existing project datalumos_id={existing_id}")
            project_url = self._project_url(existing_id)
            page.goto(project_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=120000)
            from upload.DataLumosAuthenticator import wait_for_human_verification
            wait_for_human_verification(page, timeout=60000)
            workspace_id = existing_id
        else:
            Logger.info("Navigating to DataLumos workspace")
            page.goto(self.WORKSPACE_URL, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle", timeout=120000)
            
            from upload.DataLumosAuthenticator import wait_for_human_verification
            wait_for_human_verification(page, timeout=60000)
            
            new_project_btn = page.locator(".btn > span:nth-child(3)")
            form_filler.wait_for_obscuring_elements()
            new_project_btn.click()
            
            form_filler.fill_title(self._get_field(project, "title"))
            
            wait_for_human_verification(page, timeout=60000)
            
            workspace_id = self._extract_workspace_id(page.url)
            if not workspace_id:
                raise RuntimeError(f"Could not extract workspace ID from URL: {page.url}")
            
            Logger.info(f"Created project with workspace ID: {workspace_id}")
            Storage.update_record(drpid, {"datalumos_id": workspace_id})
        
        form_filler.expand_all_sections()
        
        agencies = [f for f in [self._get_field(project, "agency"), self._get_field(project, "office")] if f]
        if agencies:
            form_filler.fill_agency(agencies)
        
        form_filler.fill_summary(self._get_field(project, "summary"))
        form_filler.fill_original_url(self._get_field(project, "source_url"))
        
        keywords_raw = self._get_field(project, "keywords")
        if keywords_raw:
            form_filler.fill_keywords(self._parse_keywords(keywords_raw))
        
        geographic = self._get_field(project, "geographic_coverage")
        if geographic:
            form_filler.fill_geographic_coverage(geographic)
        
        time_start = self._get_field(project, "time_start")
        time_end = self._get_field(project, "time_end")
        if time_start or time_end:
            form_filler.fill_time_period(time_start or None, time_end or None)
        
        data_types = self._get_field(project, "data_types")
        if data_types:
            form_filler.fill_data_types(data_types)
        
        notes = self._get_field(project, "collection_notes")
        download_date = self._get_field(project, "download_date")
        if notes or download_date:
            form_filler.fill_collection_notes(notes, download_date or None)
        
        folder_path = self._get_field(project, "folder_path")
        if folder_path:
            from upload.DataLumosFileUploader import DataLumosFileUploader
            file_uploader = DataLumosFileUploader(page, timeout=Args.upload_timeout)
            file_uploader.upload_files(folder_path)

        return workspace_id
    
    def _extract_workspace_id(self, url: str) -> Optional[str]:
        """Extract workspace ID from DataLumos URL."""
        match = re.search(r"/datalumos/(\d+)", url)
        return match.group(1) if match else None
    
    def _parse_keywords(self, keywords_raw: str) -> List[str]:
        """Parse comma-separated keywords, removing quotes and brackets."""
        cleaned = keywords_raw.replace("'", "").replace("[", "").replace("]", "").replace('"', "")
        return [p.strip() for p in cleaned.split(",") if p.strip()]
    
    def _ensure_browser(self) -> Page:
        """Ensure browser is initialized and return the page."""
        if self._page is not None:
            return self._page
        
        Logger.debug("Initializing Playwright browser")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=Args.upload_headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )
        self._context.set_default_timeout(Args.upload_timeout)
        self._page = self._context.new_page()
        return self._page
    
    def _ensure_authenticated(self) -> None:
        """Ensure user is authenticated to DataLumos."""
        if self._authenticated:
            return
        
        from upload.DataLumosAuthenticator import DataLumosAuthenticator
        
        page = self._ensure_browser()
        authenticator = DataLumosAuthenticator(page, timeout=Args.upload_timeout)
        
        if not Args.datalumos_username or not Args.datalumos_password:
            raise RuntimeError(
                "DataLumos credentials not configured. "
                "Set datalumos_username and datalumos_password in config."
            )
        
        authenticator.authenticate(Args.datalumos_username, Args.datalumos_password)
        self._authenticated = True
    
    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._page is not None:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        
        self._authenticated = False
        Logger.debug("Browser resources cleaned up")
