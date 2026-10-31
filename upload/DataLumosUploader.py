"""
DataLumos uploader module.

Implements ModuleProtocol to upload collected data to DataLumos.
Coordinates browser lifecycle, authentication, form filling, and file uploads.
"""

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.UploadIssueReporter import UploadIssueReporter
from utils.Args import Args
from utils.Errors import ProjectAbort
from utils.project_utils import get_field
from utils.inventory_status import skips_upload_file_count, upload_status_for_collected
from utils.Logger import Logger

STATUS_COLLECTED_LARGE_FILE = "collected - large file"
STATUS_UPLOADED_LARGE_FILE = "uploaded - large file"


def _agency_values_for_upload(agency: str, office: str) -> List[str]:
    """
    Build Government Agency field values for DataLumos upload.

    When office equals agency (case-insensitive after strip), only agency is
    returned so the form does not show a duplicate entry.

    Args:
        agency: Project agency name (may be empty).
        office: Project office name (may be empty).

    Returns:
        Non-empty values to pass to ``fill_agency``, agency first then office.
    """
    agency_clean = (agency or "").strip()
    office_clean = (office or "").strip()
    if not agency_clean and not office_clean:
        return []
    if not office_clean:
        return [agency_clean] if agency_clean else []
    if not agency_clean:
        return [office_clean]
    if agency_clean.casefold() == office_clean.casefold():
        return [agency_clean]
    return [agency_clean, office_clean]


def _success_status_after_upload(prior_status: str) -> str:
    """Map pre-upload status to post-upload status."""
    if prior_status == STATUS_COLLECTED_LARGE_FILE:
        return STATUS_UPLOADED_LARGE_FILE
    return upload_status_for_collected(prior_status)


def _is_large_file_status(status: str) -> bool:
    """Return True when the first upload must not compare file counts."""
    return skips_upload_file_count(status)


def _warn_if_num_files_mismatch(
    reporter: UploadIssueReporter,
    project: Dict[str, Any],
    upload_batches: int,
    *,
    used_zip: bool = False,
) -> None:
    """Stop this project when collected ``num_files`` does not match upload batch count.

    Zip imports skip this check; publish later compares the full folder tree.
    Large-file projects also skip it: ``num_files`` includes catalog files that
    were not downloaded, and the upload sends only what is on disk.

    Raises:
        ProjectAbort: When the counts differ. The error is already recorded.
    """
    if used_zip or _is_large_file_status(str(project.get("status") or "")):
        return
    nf_raw = project.get("num_files")
    if nf_raw is None:
        return
    try:
        expected_files = int(nf_raw)
    except (TypeError, ValueError):
        return
    if expected_files == upload_batches:
        return
    message = (
        f"Upload batch count ({upload_batches}) does not match "
        f"num_files from collection ({expected_files})."
    )
    reporter.error(message)
    raise ProjectAbort(message)


class DataLumosUploader:
    """
    Upload module that uploads collected project data to DataLumos.
    
    Implements ModuleProtocol. For each eligible project (``collected`` or
    ``collected - large file``), this module: authenticates, creates the
    project, posts metadata, uploads files, and updates Storage with
    datalumos_id. Creation and metadata use the deposit API unless
    ``--ui-upload`` selects the browser form.

    Not eligible: ``collected - external archive``, ``collected - file pending``,
    or other collected variants.

    Prerequisites: status in (``collected``, ``collected - large file``) and no errors
    Success status: ``uploaded``, or ``uploaded - large file`` when the large-file
    variant was collected (publisher excludes that status).
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

        prior_status = (project.get("status") or "").strip()

        errors = self._validate_project(project)
        if errors:
            for error in errors:
                reporter.error(error)
            return

        try:
            datalumos_id = self._upload_project(project, drpid, reporter)
            success_status = _success_status_after_upload(prior_status)
            Storage.update_record(drpid, {
                "datalumos_id": datalumos_id,
                "status": success_status,
            })
            _mark_downloaded_files_uploaded(drpid)
            Logger.info(
                f"Upload completed for DRPID={drpid}, datalumos_id={datalumos_id}, "
                f"status={success_status}"
            )
        except ProjectAbort:
            return
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

        The deposit API creates the project and posts metadata. ``--ui-upload``
        keeps the browser form. Files still upload from the project page.

        Returns:
            The DataLumos workspace ID.
        """
        if Args.upload_via_ui:
            Logger.info("Uploading via the DataLumos form")
            return self._upload_project_via_form(project, drpid, reporter)
        return self._upload_project_via_api(project, drpid, reporter)

    def _upload_project_via_api(
        self,
        project: Dict[str, Any],
        drpid: int,
        reporter: UploadIssueReporter,
    ) -> str:
        """Create and fill through the deposit API, then upload files."""
        page = self._session.ensure_browser()
        self._session.ensure_authenticated(reporter=reporter)
        from upload.DepositProjectUpload import DepositProjectUpload

        deposit = DepositProjectUpload(page)
        started = time.perf_counter()
        try:
            workspace_id = deposit.create(project, reporter)
            Logger.info(f"Created project with workspace ID: {workspace_id}")
            Storage.update_record(drpid, {"datalumos_id": workspace_id})
            deposit.fill(workspace_id, project)
        finally:
            Logger.info(
                "Deposit API create and metadata took %.1fs",
                time.perf_counter() - started,
            )
        self._upload_folder(page, project, reporter, workspace_id)
        return workspace_id

    def _upload_project_via_form(
        self,
        project: Dict[str, Any],
        drpid: int,
        reporter: UploadIssueReporter,
    ) -> str:
        """Create the project and fill metadata by clicking the workspace form."""
        page = self._session.ensure_browser()
        self._session.ensure_authenticated(reporter=reporter)
        from upload.FormProjectUpload import FormProjectUpload

        workspace_id = FormProjectUpload(page, self.WORKSPACE_URL).create_and_fill(
            project, drpid, reporter
        )
        self._upload_folder(page, project, reporter)
        return workspace_id

    def _upload_folder(
        self,
        page: Any,
        project: Dict[str, Any],
        reporter: UploadIssueReporter,
        workspace_id: Optional[str] = None,
    ) -> None:
        """Upload the project folder from the open project page."""
        folder_path = get_field(project, "folder_path")
        if not folder_path:
            return
        if workspace_id:
            self._open_project_page(page, workspace_id, reporter)
        from upload.DataLumosFileUploader import DataLumosFileUploader

        file_uploader = DataLumosFileUploader(
            page, timeout=Args.upload_timeout, reporter=reporter
        )
        used_zip = file_uploader.uses_zip_import(folder_path)
        file_uploader.upload_files(folder_path)
        _warn_if_num_files_mismatch(
            reporter,
            project,
            file_uploader.count_upload_batches(folder_path),
            used_zip=used_zip,
        )

    def _open_project_page(
        self,
        page: Any,
        workspace_id: str,
        reporter: UploadIssueReporter,
    ) -> None:
        """Open the project workspace so the file modal can run."""
        from upload.DataLumosAuthenticator import wait_for_human_verification
        from upload.UploadLargeFiles import WORKSPACE_LOAD_TIMEOUT_MS

        Logger.info(f"Opening DataLumos project {workspace_id} for file upload")
        page.goto(self._project_url(workspace_id), wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=WORKSPACE_LOAD_TIMEOUT_MS)
        wait_for_human_verification(page, timeout=60000, reporter=reporter)

    def _extract_workspace_id(self, url: str) -> Optional[str]:
        """Extract workspace ID from DataLumos URL."""
        match = re.search(r"/datalumos/(\d+)", url)
        return match.group(1) if match else None
    
    def _parse_keywords(self, keywords_raw: str) -> List[str]:
        """Parse keywords split on commas or semicolons; strip ampersands from tokens."""
        cleaned = keywords_raw.replace("'", "").replace("[", "").replace("]", "").replace('"', "")
        parts = re.split(r"[,;]+", cleaned)
        return [t for p in parts if (t := p.strip().strip("&").strip())]


def _mark_downloaded_files_uploaded(drpid: int) -> None:
    """Mark catalog rows that were on disk for the first upload."""
    from storage.ProjectFileStore import ProjectFileStore

    store = ProjectFileStore.from_storage()
    paths = [row.relative_path for row in store.list_for_project(drpid) if row.downloaded]
    if paths:
        store.mark_uploaded(drpid, paths)
