"""
Upload catalog files that were downloaded after the first DataLumos upload.
"""

from __future__ import annotations

from pathlib import Path

from storage import Storage
from storage.ProjectFileStore import ProjectFileRow, ProjectFileStore
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.UploadIssueReporter import UploadIssueReporter
from upload.UploadLargeFiles import UPLOAD_LARGE_FILES_TIMEOUT_MS, WORKSPACE_LOAD_TIMEOUT_MS
from utils.Args import Args
from utils.Errors import ProjectAbort
from utils.Logger import Logger
from utils.inventory_status import STATUS_DOWNLOADED, STATUS_FINISH_WAIT
from utils.project_utils import get_field


class ResumeUpload:
    """
    Send files that ``resume_download`` added and the first upload did not.

    Prerequisites: ``downloaded`` and no errors.
    Success status: ``finish wait``.
    """

    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"

    def __init__(self) -> None:
        """Initialize the browser session."""
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        """
        Upload pending ``project_files`` rows to the existing DataLumos project.

        Args:
            drpid: Project DRPID.
        """
        Logger.info("Starting resume_upload for DRPID=%s", drpid)
        reporter = UploadIssueReporter(drpid)
        project = Storage.get(drpid)
        if project is None:
            reporter.error(f"Project with DRPID={drpid} not found in Storage")
            return
        if (project.get("status") or "").strip() != STATUS_DOWNLOADED:
            reporter.error(f"Expected status {STATUS_DOWNLOADED!r}")
            return
        if not get_field(project, "datalumos_id"):
            reporter.error("Missing datalumos_id")
            return
        folder = Path(get_field(project, "folder_path") or "")
        if not folder.is_dir():
            reporter.error(f"Folder path is not a directory: {folder}")
            return
        try:
            self._upload_pending(drpid, project, folder, reporter)
            Storage.update_record(drpid, {"status": STATUS_FINISH_WAIT})
            Logger.info("resume_upload completed for DRPID=%s", drpid)
        except ProjectAbort:
            return
        except Exception as exc:
            reporter.error(f"resume_upload failed: {exc}")
            raise
        finally:
            self._session.close()

    def _upload_pending(
        self,
        drpid: int,
        project: dict,
        folder: Path,
        reporter: UploadIssueReporter,
    ) -> None:
        """Upload not-yet-uploaded files in one batch and mark them after it succeeds."""
        store = ProjectFileStore.from_storage()
        pending = store.list_pending_uploads(drpid)
        if not pending:
            Logger.info("No new files to upload for DRPID=%s", drpid)
            return
        paths = self._pending_paths(folder, pending, reporter)
        page = self._session.ensure_browser()
        self._session.ensure_authenticated(reporter=reporter)
        workspace_id = get_field(project, "datalumos_id")
        project_url = (
            f"{self.WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"
        )
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=WORKSPACE_LOAD_TIMEOUT_MS)
        from upload.DataLumosAuthenticator import wait_for_human_verification
        from upload.DataLumosFileUploader import DataLumosFileUploader

        wait_for_human_verification(page, timeout=60000, reporter=reporter)
        page.context.set_default_timeout(UPLOAD_LARGE_FILES_TIMEOUT_MS)
        uploader = DataLumosFileUploader(
            page,
            timeout=UPLOAD_LARGE_FILES_TIMEOUT_MS,
            upload_wait_timeout=UPLOAD_LARGE_FILES_TIMEOUT_MS,
            reporter=reporter,
            skip_busy_wait_on_close=True,
        )
        Logger.info(
            "Uploading %s file(s) not yet on DataLumos for DRPID=%s",
            len(paths),
            drpid,
        )
        uploader.upload_paths_preserving_folders(folder, paths)
        store.mark_uploaded(drpid, [row.relative_path for row in pending])

    def _pending_paths(
        self,
        folder: Path,
        pending: list[ProjectFileRow],
        reporter: UploadIssueReporter,
    ) -> list[Path]:
        """Return on-disk paths for pending rows, stopping when one is missing."""
        paths: list[Path] = []
        for row in pending:
            path = folder / row.relative_path
            if not path.is_file():
                reporter.error(f"Missing file to upload: {row.relative_path}")
                raise ProjectAbort(row.relative_path)
            paths.append(path)
        return paths
