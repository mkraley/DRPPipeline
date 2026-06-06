"""
Upload large files module.

For projects at ``uploaded - large file`` with total size under 25 GB: download
missing large publication files via aria2, then upload them to the existing
DataLumos project.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from collectors.UsfsAria2Export import (
    DEFAULT_ARIA2_OUTPUT_DIR,
    MAX_DOWNLOAD_BYTES,
    aria2_argv_for_download,
    drpid_cmd_path,
    entries_for_publication_files,
    out_name_from_aria2_cmd_line,
    parse_aria2c_lines_from_cmd_file,
    write_drpid_aria2_cmd,
)
from collectors.UsfsMetadataExtractor import parse_data_access_links
from storage import Storage
from upload.DataLumosBrowserSession import DataLumosBrowserSession
from upload.UploadIssueReporter import UploadIssueReporter
from utils.Args import Args
from utils.file_utils import parse_file_size_to_bytes
from utils.Logger import Logger
from utils.project_utils import get_field
from utils.url_utils import BROWSER_HEADERS, fetch_page_body

STATUS_UPLOADED_LARGE_FILE = "uploaded - large file"
STATUS_FINISH_WAIT = "finish wait"
MAX_PROJECT_FILE_SIZE_BYTES = 25 * 1024**3
DEFAULT_SUMMARY_INTERVAL = 0
UPLOAD_LARGE_FILES_TIMEOUT_MS = 2 * 60 * 60 * 1000  # 2 hours per file / UI action


def project_under_size_limit(project: Dict[str, Any]) -> bool:
    """Return True when ``file_size`` is present and below the 25 GB cap."""
    size_bytes = parse_file_size_to_bytes(project.get("file_size"))
    if size_bytes is None:
        return False
    return size_bytes < MAX_PROJECT_FILE_SIZE_BYTES


def resolve_output_folder(drpid: int, folder_path: str | None) -> Path:
    if folder_path:
        return Path(folder_path)
    return Path(Args.base_output_dir) / f"DRP{drpid:06d}"


def log_path_for_download(log_root: Path, drpid: int, out_name: str) -> Path:
    safe = re.sub(r'[<>:"/\\|?*]', "_", out_name)
    return log_root / f"DRP{drpid:06d}" / f"{safe}.log"


def planned_out_names(aria2_lines: Sequence[str]) -> List[str]:
    """Extract output filenames from aria2 command lines."""
    names: List[str] = []
    for line in aria2_lines:
        name = out_name_from_aria2_cmd_line(line)
        if name:
            names.append(name)
    return names


def large_files_on_disk(drpid: int, project: Dict[str, Any]) -> List[str]:
    """
    Return catalog-listed large publication filenames that exist on disk.

    Used when there is nothing left to download but large files still need
    uploading to DataLumos.
    """
    source_url = get_field(project, "source_url")
    if not source_url:
        return []

    status, body, _, _ = fetch_page_body(source_url)
    if status != 200 or not body:
        return []

    links = parse_data_access_links(body, source_url)
    folder = resolve_output_folder(drpid, get_field(project, "folder_path") or None)
    entries = entries_for_publication_files(
        links.get("publication_files", []),
        folder,
        min_bytes=MAX_DOWNLOAD_BYTES,
        missing_only=False,
    )
    return [entry.out_name for entry in entries if (folder / entry.out_name).is_file()]


def ensure_aria2_cmd(drpid: int, project: Dict[str, Any]) -> Tuple[Path, List[str]]:
    """
    Ensure ``aria2_inputs/DRP######.cmd`` exists and return its aria2c lines.

    Creates the batch file from the USFS catalog when missing or empty.
    """
    cmd_path = drpid_cmd_path(drpid, DEFAULT_ARIA2_OUTPUT_DIR)
    if cmd_path.is_file():
        lines = parse_aria2c_lines_from_cmd_file(cmd_path)
        if lines:
            return cmd_path, lines

    source_url = get_field(project, "source_url")
    if not source_url:
        return cmd_path, []

    status, body, _, _ = fetch_page_body(source_url)
    if status != 200 or not body:
        Logger.warning(
            "Could not fetch catalog for DRPID=%s to build aria2 cmd (status=%s)",
            drpid,
            status,
        )
        return cmd_path, []

    links = parse_data_access_links(body, source_url)
    folder = resolve_output_folder(drpid, get_field(project, "folder_path") or None)
    folder.mkdir(parents=True, exist_ok=True)

    write_drpid_aria2_cmd(
        drpid,
        folder,
        links.get("publication_files", []),
        output_dir=DEFAULT_ARIA2_OUTPUT_DIR,
        user_agent=BROWSER_HEADERS["User-Agent"],
    )

    if not cmd_path.is_file():
        return cmd_path, []
    return cmd_path, parse_aria2c_lines_from_cmd_file(cmd_path)


def run_aria2_downloads(
    drpid: int,
    aria2_lines: Sequence[str],
    *,
    log_root: Path,
    summary_interval: int = DEFAULT_SUMMARY_INTERVAL,
    stop_on_error: bool = True,
) -> Tuple[int, int]:
    """
    Run aria2 downloads for one DRPID.

    Returns:
        (ok_count, fail_count)
    """
    log_dir = log_root / f"DRP{drpid:06d}"
    log_dir.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    fail_count = 0

    for index, cmd_line in enumerate(aria2_lines, start=1):
        out_name = out_name_from_aria2_cmd_line(cmd_line) or f"download_{index}"
        log_path = log_path_for_download(log_root, drpid, out_name)

        if len(aria2_lines) > 1:
            Logger.info("[%s/%s] Downloading %s", index, len(aria2_lines), out_name)

        argv = aria2_argv_for_download(
            cmd_line,
            log_path=log_path,
            summary_interval=summary_interval,
        )
        result = subprocess.run(argv, check=False)
        if result.returncode == 0:
            ok_count += 1
        else:
            fail_count += 1
            Logger.error(
                "Download failed for DRPID=%s file=%s exit=%s log=%s",
                drpid,
                out_name,
                result.returncode,
                log_path,
            )
            if stop_on_error:
                break

    if fail_count:
        Logger.error(
            "DRPID=%s downloads: %s ok, %s failed — logs in %s",
            drpid,
            ok_count,
            fail_count,
            log_dir,
        )
    return ok_count, fail_count


class UploadLargeFiles:
    """
    Download missing large USFS files and upload them to an existing DataLumos project.

    Prerequisites: status ``uploaded - large file``, ``file_size`` < 25 GB, no errors
    Success status: ``finish wait``
    """

    WORKSPACE_URL = "https://www.datalumos.org/datalumos/workspace"

    def __init__(self) -> None:
        self._session = DataLumosBrowserSession()

    def run(self, drpid: int) -> None:
        Logger.info("Starting upload_large_files for DRPID=%s", drpid)
        reporter = UploadIssueReporter(drpid)

        project = Storage.get(drpid)
        if project is None:
            reporter.error(f"Project with DRPID={drpid} not found in Storage")
            return

        status = (project.get("status") or "").strip()
        if status != STATUS_UPLOADED_LARGE_FILE:
            reporter.error(
                f"Expected status {STATUS_UPLOADED_LARGE_FILE!r}, got {status!r}"
            )
            return

        if not project_under_size_limit(project):
            reporter.error(
                "Project file_size is missing or >= 25 GB; skipping large-file upload"
            )
            return

        errors = self._validate_project(project)
        if errors:
            for error in errors:
                reporter.error(error)
            return

        folder = resolve_output_folder(drpid, get_field(project, "folder_path") or None)
        if not folder.is_dir():
            reporter.error(f"Folder path is not a directory: {folder}")
            return

        try:
            _, aria2_lines = ensure_aria2_cmd(drpid, project)
            download_names = planned_out_names(aria2_lines)

            if aria2_lines:
                log_root = Path(Args.base_output_dir) / "logs"
                _, fail_count = run_aria2_downloads(drpid, aria2_lines, log_root=log_root)
                if fail_count:
                    reporter.error(
                        f"aria2 download failed for {fail_count} file(s); see logs under {log_root}"
                    )
                    return

            upload_names = download_names or large_files_on_disk(drpid, project)
            if not upload_names:
                reporter.error(
                    "No large files to upload (nothing to download and none found on disk)"
                )
                return

            file_paths = [folder / name for name in upload_names]
            missing = [str(p) for p in file_paths if not p.is_file()]
            if missing:
                reporter.error(f"Missing expected file(s) on disk: {', '.join(missing)}")
                return

            Logger.info(
                "Uploading %s large file(s) for DRPID=%s: %s",
                len(file_paths),
                drpid,
                ", ".join(p.name for p in file_paths),
            )
            self._upload_files_to_existing_project(project, drpid, file_paths, reporter)
            Storage.update_record(drpid, {"status": STATUS_FINISH_WAIT})
            Logger.info(
                "upload_large_files completed for DRPID=%s, status=%s",
                drpid,
                STATUS_FINISH_WAIT,
            )
        except Exception as exc:
            reporter.error(f"upload_large_files failed: {exc}")
            raise
        finally:
            self._session.close()

    def _validate_project(self, project: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not get_field(project, "datalumos_id"):
            errors.append("Missing datalumos_id; project must be uploaded before large files")
        folder = get_field(project, "folder_path")
        if folder:
            path = Path(folder)
            if not path.exists():
                errors.append(f"Folder path does not exist: {folder}")
            elif not path.is_dir():
                errors.append(f"Folder path is not a directory: {folder}")
        return errors

    def _project_url(self, workspace_id: str) -> str:
        return f"{self.WORKSPACE_URL}?goToLevel=project&goToPath=/datalumos/{workspace_id}#"

    def _upload_files_to_existing_project(
        self,
        project: Dict[str, Any],
        drpid: int,
        file_paths: List[Path],
        reporter: UploadIssueReporter,
    ) -> None:
        workspace_id = get_field(project, "datalumos_id")
        page = self._session.ensure_browser()
        self._session.ensure_authenticated(reporter=reporter)

        project_url = self._project_url(workspace_id)
        Logger.info("Navigating to existing DataLumos project %s", workspace_id)
        page.goto(project_url, wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle", timeout=120000)

        from upload.DataLumosAuthenticator import wait_for_human_verification

        wait_for_human_verification(page, timeout=60000, reporter=reporter)

        from upload.DataLumosFileUploader import DataLumosFileUploader

        page.context.set_default_timeout(UPLOAD_LARGE_FILES_TIMEOUT_MS)
        file_uploader = DataLumosFileUploader(
            page,
            timeout=UPLOAD_LARGE_FILES_TIMEOUT_MS,
            upload_wait_timeout=UPLOAD_LARGE_FILES_TIMEOUT_MS,
            reporter=reporter,
            skip_busy_wait_on_close=True,
        )
        file_uploader.upload_file_paths(file_paths)
