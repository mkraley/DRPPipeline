"""
DataLumos uploader module.

Implements ModuleProtocol to upload collected data to DataLumos.
Coordinates browser lifecycle, authentication, form filling, and file uploads.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.UploadIssueReporter import UploadIssueReporter
from collectors.UsfsCollector import STATUS_COLLECTED_LARGE_FILE, STATUS_UPLOADED_LARGE_FILE
from utils.Args import Args
from utils.project_utils import get_field
from utils.Logger import Logger


def _warn_if_num_files_mismatch(
    reporter: UploadIssueReporter,
    project: Dict[str, Any],
    upload_batches: int,
) -> None:
    """Record a warning when collected ``num_files`` does not match upload batch count."""
    nf_raw = project.get("num_files")
    if nf_raw is None:
        return
    try:
        expected_files = int(nf_raw)
    except (TypeError, ValueError):
        return
    if expected_files == upload_batches:
        return
    reporter.warn(
        f"Upload batch count ({upload_batches}) does not match "
        f"num_files from collection ({expected_files}). "
        "(Zip import counts as 1; num_files is top-level file count.)"
    )


class DataLumosUploader:
    """
    Upload module that uploads collected project data to DataLumos.
    
    Implements ModuleProtocol. For each eligible project (status="collected"),
    this module: authenticates, creates project, fills form fields,
    and updates Storage with datalumos_id.
    
    Prerequisites: status="collected" and no errors
    Success status: status="upload"
    """
    
    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"
    
    def __init__(self) -> None:
        """Initialize the DataLumos uploader. Config from Args."""
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        """
        Run the upload process for a single project.
        
        Implements ModuleProtocol. Gets project from Storage, validates,
        uploads to DataLumos, and updates Storage on success.
        
        Args:
            drpid: The DRPID of the project to upload.
        """
        Logger.info(f"Starting upload for DRPID={drpid}")
        reporter = UploadIssueReporter(drpid)
        
        project = Storage.get(drpid)
        if project is None:
            reporter.error(f"Project with DRPID={drpid} not found in Storage")
            return
        
        errors = self._validate_project(project)
        if errors:
            for error in errors:
                reporter.error(error)
            return

        try:
            source_url = get_field(project, "source_url")
            if source_url:
                page = self._session.ensure_browser()
                from upload.GWDANominator import GWDANominator

                nominator = GWDANominator(page, timeout=Args.upload_timeout)
                success, error = nominator.nominate(source_url)
                if not success:
                    reporter.error(error or "GWDA nomination failed")
                    return

            try:
                datalumos_id = self._upload_project(project, drpid, reporter)
                upload_status = (
                    STATUS_UPLOADED_LARGE_FILE
                    if project.get("status") == STATUS_COLLECTED_LARGE_FILE
                    else "uploaded"
                )
                Storage.update_record(drpid, {
                    "datalumos_id": datalumos_id,
                    "status": upload_status,
                })
                Logger.info(
                    f"Upload completed for DRPID={drpid}, datalumos_id={datalumos_id}, "
                    f"status={upload_status}"
                )
            except Exception as e:
                reporter.error(f"Upload failed: {e}")
                raise
        finally:
            self._session.close()
    
    def _validate_project(self, project: Dict[str, Any]) -> list[str]:
        """Validate required fields. Returns list of error messages."""
        errors: list[str] = []
        if not get_field(project, "title"):
            errors.append("Missing required field: title")
        if not get_field(project, "summary"):
            errors.append("Missing required field: summary")
        
        folder = get_field(project, "folder_path")
        if folder:
            path = Path(folder)
            if not path.exists():
                errors.append(f"Folder path does not exist: {folder}")
            elif not path.is_dir():
                errors.append(f"Folder path is not a directory: {folder}")
        
        return errors
    
    def _project_url(self, workspace_id: str) -> str:
        """Build URL for a DataLumos project page."""
        return f"{self.WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"

    def _upload_project(
        self,
        project: Dict[str, Any],
        drpid: int,
        reporter: UploadIssueReporter,
    ) -> str:
        """
        Upload a project to DataLumos.

        Navigates to workspace, creates a new project, saves datalumos_id to
        Storage, then fills the form.

        Returns:
            The DataLumos workspace ID.
        """
        page = self._session.ensure_browser()
        self._session.ensure_authenticated(reporter=reporter)

        from upload.DataLumosFormFiller import DataLumosFormFiller

        form_filler = DataLumosFormFiller(
            page, timeout=Args.upload_timeout, reporter=reporter
        )

        Logger.info("Navigating to DataLumos workspace")
        page.goto(self.WORKSPACE_URL, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=120000)

        from upload.DataLumosAuthenticator import wait_for_human_verification
        wait_for_human_verification(page, timeout=60000, reporter=reporter)

        new_project_btn = page.locator(".btn > span:nth-child(3)")
        form_filler.wait_for_obscuring_elements()
        new_project_btn.click()

        form_filler.fill_title(get_field(project, "title"))

        wait_for_human_verification(page, timeout=60000, reporter=reporter)

        workspace_id = self._extract_workspace_id(page.url)
        if not workspace_id:
            raise RuntimeError(f"Could not extract workspace ID from URL: {page.url}")

        Logger.info(f"Created project with workspace ID: {workspace_id}")
        Storage.update_record(drpid, {"datalumos_id": workspace_id})

        form_filler.expand_all_sections()
        
        agencies = [f for f in [get_field(project, "agency"), get_field(project, "office")] if f]
        if agencies:
            form_filler.fill_agency(agencies)
        
        form_filler.fill_summary(get_field(project, "summary"))
        form_filler.fill_original_url(get_field(project, "source_url"))

        keywords_raw = get_field(project, "keywords")
        if keywords_raw:
            form_filler.fill_keywords(self._parse_keywords(keywords_raw))
        
        geographic = get_field(project, "geographic_coverage")
        if geographic:
            form_filler.fill_geographic_coverage(geographic)
        
        time_start = get_field(project, "time_start")
        time_end = get_field(project, "time_end")
        if time_start or time_end:
            form_filler.fill_time_period(time_start or None, time_end or None)
        
        data_types = get_field(project, "data_types")
        if data_types:
            form_filler.fill_data_types(data_types)
        
        notes = get_field(project, "collection_notes")
        download_date = get_field(project, "download_date")
        if notes or download_date:
            form_filler.fill_collection_notes(notes, download_date or None)
        
        folder_path = get_field(project, "folder_path")
        if folder_path:
            from upload.DataLumosFileUploader import DataLumosFileUploader
            file_uploader = DataLumosFileUploader(
                page, timeout=Args.upload_timeout, reporter=reporter
            )
            upload_batches = file_uploader.count_upload_batches(folder_path)
            file_uploader.upload_files(folder_path)
            _warn_if_num_files_mismatch(reporter, project, upload_batches)

        return workspace_id
    
    def _extract_workspace_id(self, url: str) -> Optional[str]:
        """Extract workspace ID from DataLumos URL."""
        match = re.search(r"/datalumos/(\d+)", url)
        return match.group(1) if match else None
    
    def _parse_keywords(self, keywords_raw: str) -> List[str]:
        """Parse keywords split on commas or semicolons; strip ampersands from tokens."""
        cleaned = keywords_raw.replace("'", "").replace("[", "").replace("]", "").replace('"', "")
        parts = re.split(r"[,;]+", cleaned)
        return [t for p in parts if (t := p.strip().strip("&").strip())]
