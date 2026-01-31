"""
Upload module for DRP Pipeline.

Implements ModuleProtocol to upload collected data to DataLumos.
Orchestrates authentication, form filling, and file uploads.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from storage import Storage
from utils.Args import Args
from utils.Errors import record_error, record_warning
from utils.Logger import Logger


class Upload:
    """
    Upload module that uploads collected project data to DataLumos.
    
    Implements ModuleProtocol. For each eligible project (status="collector"),
    this module:
    1. Retrieves project data from Storage
    2. Validates required fields
    3. Authenticates to DataLumos
    4. Creates a new project and fills form fields
    5. Uploads files from the project folder
    6. Updates Storage with datalumos_id and status
    
    Prerequisites: status="collector" and no errors
    Success status: status="upload"
    """
    
    def __init__(self) -> None:
        """Initialize the Upload module."""
        self._uploader: Optional["DataLumosUploader"] = None
    
    def run(self, drpid: int) -> None:
        """
        Run the upload process for a single project.
        
        Args:
            drpid: The DRPID of the project to upload.
            
        The module will:
        - Get project data from Storage
        - Validate required fields (title, summary)
        - Initialize Playwright and authenticate to DataLumos
        - Create project and fill all form fields
        - Upload files from folder_path
        - Extract datalumos_id from URL
        - Update Storage with datalumos_id and status="upload"
        """
        Logger.info(f"Starting upload for DRPID={drpid}")
        
        # Get project data from Storage
        project = Storage.get(drpid)
        if project is None:
            record_error(drpid, f"Project with DRPID={drpid} not found in Storage")
            return
        
        # Validate required fields
        validation_errors = self._validate_project(project)
        if validation_errors:
            for error in validation_errors:
                record_error(drpid, error)
            return
        
        try:
            # Import here to avoid circular imports and allow lazy loading
            from upload.DataLumosUploader import DataLumosUploader
            
            # Initialize uploader with credentials from config
            self._uploader = DataLumosUploader(
                username=Args.datalumos_username,
                password=Args.datalumos_password,
                headless=Args.upload_headless,
                timeout=Args.upload_timeout,
            )
            
            # Perform the upload
            datalumos_id = self._uploader.upload_project(project)
            
            # Update Storage with success
            Storage.update_record(drpid, {
                "datalumos_id": datalumos_id,
                "status": "upload",
            })
            
            Logger.info(f"Upload completed for DRPID={drpid}, datalumos_id={datalumos_id}")
            
        except Exception as e:
            record_error(drpid, f"Upload failed: {e}")
            raise
        finally:
            # Clean up browser resources
            if self._uploader is not None:
                self._uploader.close()
    
    def _validate_project(self, project: Dict[str, Any]) -> list[str]:
        """
        Validate that a project has all required fields for upload.
        
        Args:
            project: Project data dictionary from Storage
            
        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: list[str] = []
        
        # Required fields
        if not project.get("title"):
            errors.append("Missing required field: title")
        
        if not project.get("summary"):
            errors.append("Missing required field: summary")
        
        # Folder path should exist if specified
        folder_path = project.get("folder_path")
        if folder_path:
            path = Path(folder_path)
            if not path.exists():
                errors.append(f"Folder path does not exist: {folder_path}")
            elif not path.is_dir():
                errors.append(f"Folder path is not a directory: {folder_path}")
        
        return errors
