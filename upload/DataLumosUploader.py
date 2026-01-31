"""
DataLumos uploader core logic.

Coordinates all upload steps: browser lifecycle, authentication,
form filling, and file uploads.
"""

import re
from typing import Any, Dict, List, Optional

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from utils.Logger import Logger


class DataLumosUploader:
    """
    Core uploader class that coordinates DataLumos upload operations.
    
    Manages Playwright browser lifecycle and orchestrates:
    - Authentication via DataLumosAuthenticator
    - Form filling via DataLumosFormFiller  
    - File uploads via DataLumosFileUploader
    
    Usage:
        uploader = DataLumosUploader(username, password)
        try:
            datalumos_id = uploader.upload_project(project_data)
        finally:
            uploader.close()
    """
    
    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
    
    def __init__(
        self,
        username: str,
        password: str,
        headless: bool = False,
        timeout: int = 60000,
    ) -> None:
        """
        Initialize the DataLumos uploader.
        
        Args:
            username: DataLumos username/email for authentication
            password: DataLumos password for authentication
            headless: Whether to run browser in headless mode
            timeout: Default timeout in milliseconds for operations
        """
        self._username = username
        self._password = password
        self._headless = headless
        self._timeout = timeout
        
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._authenticated = False
    
    def upload_project(self, project: Dict[str, Any]) -> str:
        """
        Upload a project to DataLumos.
        
        Args:
            project: Project data dictionary containing fields to upload:
                - title: Project title (required)
                - summary: Project summary/description (required)
                - agency: Government agency name
                - office: Government office name
                - source_url: Original distribution URL
                - keywords: Comma-separated keywords
                - time_start: Time period start date
                - time_end: Time period end date
                - data_types: Data type selection
                - collection_notes: Collection notes
                - download_date: Download date for collection notes
                - folder_path: Path to folder containing files to upload
                
        Returns:
            The DataLumos workspace ID (datalumos_id) for the created project
            
        Raises:
            RuntimeError: If upload fails
        """
        page = self._ensure_browser()
        self._ensure_authenticated()
        
        from upload.DataLumosFormFiller import DataLumosFormFiller
        
        form_filler = DataLumosFormFiller(page, timeout=self._timeout)
        
        # Navigate to workspace
        Logger.info("Navigating to DataLumos workspace")
        page.goto(self.WORKSPACE_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=120000)
        
        # Click New Project button
        new_project_btn = page.locator(".btn > span:nth-child(3)")
        new_project_btn.wait_for(state="visible", timeout=360000)
        form_filler.wait_for_obscuring_elements()
        new_project_btn.click()
        
        # Fill title (creates project and navigates to workspace)
        title = (project.get("title") or "").strip()
        form_filler.fill_title(title)
        
        # Extract workspace ID from URL
        current_url = page.url
        workspace_id = self._extract_workspace_id(current_url)
        if not workspace_id:
            raise RuntimeError(f"Could not extract workspace ID from URL: {current_url}")
        
        Logger.info(f"Created project with workspace ID: {workspace_id}")
        
        # Expand all form sections
        form_filler.expand_all_sections()
        
        # Fill agency and office (two add-value calls)
        agencies: List[str] = []
        agency = (project.get("agency") or "").strip()
        office = (project.get("office") or "").strip()
        if agency:
            agencies.append(agency)
        if office:
            agencies.append(office)
        if agencies:
            form_filler.fill_agency(agencies)
        
        # Fill summary
        summary = (project.get("summary") or "").strip()
        form_filler.fill_summary(summary)
        
        # Fill original distribution URL
        source_url = (project.get("source_url") or "").strip()
        form_filler.fill_original_url(source_url)
        
        # Fill keywords
        keywords_raw = (project.get("keywords") or "").strip()
        if keywords_raw:
            keywords = self._parse_keywords(keywords_raw)
            form_filler.fill_keywords(keywords)
        
        # Fill geographic coverage (if present in project - not in current schema)
        geographic = (project.get("geographic_coverage") or "").strip()
        if geographic:
            form_filler.fill_geographic_coverage(geographic)
        
        # Fill time period
        time_start = (project.get("time_start") or "").strip()
        time_end = (project.get("time_end") or "").strip()
        if time_start or time_end:
            form_filler.fill_time_period(time_start or None, time_end or None)
        
        # Fill data types
        data_types = (project.get("data_types") or "").strip()
        if data_types:
            form_filler.fill_data_types(data_types)
        
        # Fill collection notes
        collection_notes = (project.get("collection_notes") or "").strip()
        download_date = (project.get("download_date") or "").strip()
        if collection_notes or download_date:
            form_filler.fill_collection_notes(collection_notes, download_date or None)
        
        # File upload handled in Phase 4
        folder_path = (project.get("folder_path") or "").strip()
        if folder_path:
            Logger.debug(f"File upload from {folder_path} deferred to Phase 4")
        
        return workspace_id
    
    def _extract_workspace_id(self, url: str) -> Optional[str]:
        """
        Extract workspace ID from DataLumos URL.
        
        Args:
            url: Current page URL
            
        Returns:
            Workspace ID string, or None if not found
        """
        match = re.search(r"/datalumos/(\d+)", url)
        return match.group(1) if match else None
    
    def _parse_keywords(self, keywords_raw: str) -> List[str]:
        """
        Parse keywords string into list of individual keywords.
        
        Removes quotes and brackets, splits by comma.
        
        Args:
            keywords_raw: Raw keywords string (e.g. from CSV or DB)
            
        Returns:
            List of trimmed keyword strings
        """
        cleaned = keywords_raw.replace("'", "").replace("[", "").replace("]", "").replace('"', "")
        parts = cleaned.split(",")
        return [p.strip() for p in parts if p.strip()]
    
    def _ensure_browser(self) -> Page:
        """
        Ensure browser is initialized and return the page.
        
        Initializes Playwright and browser if not already done.
        
        Returns:
            The Playwright Page object
        """
        if self._page is not None:
            return self._page
        
        Logger.debug("Initializing Playwright browser")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        self._context = self._browser.new_context()
        self._context.set_default_timeout(self._timeout)
        self._page = self._context.new_page()
        
        return self._page
    
    def _ensure_authenticated(self) -> None:
        """
        Ensure user is authenticated to DataLumos.
        
        Performs authentication if not already done.
        
        Raises:
            RuntimeError: If authentication fails
        """
        if self._authenticated:
            return
        
        from upload.DataLumosAuthenticator import DataLumosAuthenticator
        
        page = self._ensure_browser()
        authenticator = DataLumosAuthenticator(page, timeout=self._timeout)
        
        if not self._username or not self._password:
            raise RuntimeError(
                "DataLumos credentials not configured. "
                "Set datalumos_username and datalumos_password in config."
            )
        
        authenticator.authenticate(self._username, self._password)
        self._authenticated = True
    
    def close(self) -> None:
        """
        Close the browser and clean up resources.
        
        Safe to call multiple times.
        """
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
