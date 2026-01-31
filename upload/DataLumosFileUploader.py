"""
DataLumos file upload handler.

Handles uploading files to a DataLumos project using Playwright.
"""

from pathlib import Path
from typing import List

from playwright.sync_api import Page

from utils.Logger import Logger


class DataLumosFileUploader:
    """
    Handles file uploads to DataLumos.
    
    Uses Playwright's file input handling to upload files
    and waits for upload completion.
    """
    
    def __init__(self, page: Page, timeout: int = 120000) -> None:
        """
        Initialize the file uploader.
        
        Args:
            page: Playwright Page object
            timeout: Default timeout in milliseconds (longer for file uploads)
        """
        self._page = page
        self._timeout = timeout
    
    def upload_files(self, folder_path: str) -> None:
        """
        Upload all files from a folder to the current DataLumos project.
        
        Args:
            folder_path: Path to folder containing files to upload
            
        Raises:
            FileNotFoundError: If folder doesn't exist
            RuntimeError: If upload fails
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("DataLumosFileUploader.upload_files() not yet implemented")
    
    def get_file_paths(self, folder_path: str) -> List[Path]:
        """
        Get list of file paths to upload from a folder.
        
        Args:
            folder_path: Path to folder containing files
            
        Returns:
            List of Path objects for files to upload
            
        Raises:
            FileNotFoundError: If folder doesn't exist
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise FileNotFoundError(f"Folder not found: {folder_path}")
        if not folder.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {folder_path}")
        
        # Get all files (not subdirectories)
        files = [f for f in folder.iterdir() if f.is_file()]
        Logger.debug(f"Found {len(files)} files in {folder_path}")
        return files
    
    def wait_for_upload_completion(self, file_count: int) -> None:
        """
        Wait for all file uploads to complete.
        
        Looks for "File added to queue for upload." messages
        to match the expected file count.
        
        Args:
            file_count: Number of files being uploaded
            
        Raises:
            TimeoutError: If uploads don't complete in time
        """
        # TODO: Implement in Phase 4
        raise NotImplementedError("DataLumosFileUploader.wait_for_upload_completion() not yet implemented")
